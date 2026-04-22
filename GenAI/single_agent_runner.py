"""
Single Agent Runner - Ablation Baseline
========================================

Ablation study: replaces the two-agent pipeline (Analysis Agent + Context Planner)
with a single agent that has access to all tools from both ablation agents but
receives no system instructions and no injected context -- only the PR title and body.

This isolates the effect of agent decomposition: does splitting reasoning across
two specialized agents outperform one generalist agent with equivalent tool access?

================================================================================
USAGE
================================================================================

    # Single PR
    python -m GenAI.single_agent_runner <pr_directory>

    # With options
    python -m GenAI.single_agent_runner <pr_directory> -m gpt-5.2-2025-12-11 -q

Options:
    -m, --model     OpenAI model (overrides agents_config.toml)
    -q, --quiet     Quiet mode

Output is written to:
    pr_dir/evals/single_agent_turn/
    ├── predicted_plan.json
    ├── token_usage.json
    ├── session_log.json
    └── ground_truth.json   (copied from pr_dir/ground_truth.json)

================================================================================
"""

import os
import json
import time
import asyncio
import argparse
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, Runner

from colorama import Fore, Style, init

from GenAI.tools import _read_file_impl, _list_directory_impl, _read_text_file
from GenAI.prompts.single_agent import get_single_agent_prompt
from GenAI.utils import run_async_safely
from GenAI.config_loader import load_config
from GenAI.pr_step_planner import (
    PlannerOutput,
    AgentTokenUsage,
    TokenUsageReport,
    ToolCall,
    RetryEvent,
    AgentSession,
    SessionContext,
    SessionLog,
    create_base_project_tools_ablation,
    create_context_files_tools,
    MAX_FILE_CHARS,
)
from evaluation.models import StepPlan

init(autoreset=True)
load_dotenv()

EVAL_SUBDIR = "evals/single_agent_turn"


class SingleAgentPlanner:
    """
    Single-agent ablation orchestrator.

    Runs one agent with:
    - No system instructions
    - User message = PR title + body only
    - Tools = ablation base-project tools + context-files tools (5 total)
    - Output type = PlannerOutput (same schema as the two-agent system)
    """

    def __init__(
        self,
        pr_dir: str,
        model_name: Optional[str] = None,
        verbose: bool = True,
        eval_dir: Optional[Path] = None,
        eval_subdir: Optional[str] = None,
    ):
        """
        Args:
            pr_dir: Path to the PR directory.
            model_name: Overrides the model from agents_config.toml.
            verbose: Print detailed output.
            eval_dir: Optional top-level consolidated eval folder
                      (e.g. Path("single_agent_evals/single_agent_turn")).
                      When set, save_output() copies results there under
                      <owner_repo>/<pr_NUMBER>/, mirroring the gpt_5-2_evals layout.
            eval_subdir: Override the subdirectory inside pr_dir where outputs are
                         written (default: "evals/single_agent_turn"). Use this to
                         keep results from different models separate, e.g.
                         "evals/single_agent_turn_mini".
        """
        self.pr_dir = Path(pr_dir).resolve()
        self.verbose = verbose
        self.eval_dir = Path(eval_dir).resolve() if eval_dir else None
        self._eval_subdir = eval_subdir or EVAL_SUBDIR

        cfg = load_config()
        if model_name:
            self.model_name = model_name
        else:
            sa_cfg = cfg.agents.single_agent
            self.model_name = sa_cfg.model if sa_cfg else cfg.defaults.model

        self.data_json_path = self.pr_dir / "data.json"
        self.base_project_path = self.pr_dir / "base_project"
        self.context_output_path = self.base_project_path / "context_output"
        self.masca_path = self.context_output_path / "masca_analysis.md"

        self._validate_paths()
        self.pr_data = self._load_pr_data()

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")
        self.client = AsyncOpenAI(api_key=api_key, timeout=120.0)

    def _validate_paths(self):
        if not self.pr_dir.exists():
            raise FileNotFoundError(f"PR directory not found: {self.pr_dir}")
        if not self.data_json_path.exists():
            raise FileNotFoundError(f"data.json not found: {self.data_json_path}")
        if not self.base_project_path.exists():
            raise FileNotFoundError(f"base_project not found: {self.base_project_path}")

    def _load_pr_data(self) -> dict:
        with open(self.data_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def _run_single_agent(self) -> tuple[PlannerOutput, AgentSession]:
        if self.verbose:
            print(f"\n{Fore.YELLOW}{'='*80}")
            print(f"{Fore.YELLOW}🤖 Single Agent (ablation baseline)")
            print(f"{Fore.YELLOW}{'='*80}{Style.RESET_ALL}")

        tool_call_log: list = []

        # Combined tools: ablation base-project (2) + context-files (3)
        base_tools = create_base_project_tools_ablation(self.base_project_path, tool_call_log)
        ctx_tools = create_context_files_tools(self.context_output_path, tool_call_log)
        all_tools = base_tools + ctx_tools

        MODEL = OpenAIChatCompletionsModel(
            model=self.model_name,
            openai_client=self.client,
        )

        agent = Agent(
            name="single_agent",
            instructions="",          # no system instructions
            tools=base_tools,
            model=MODEL,
            model_settings=ModelSettings(),
            output_type=PlannerOutput,
        )

        pr_title = (self.pr_data.get("title", "") or "")[:500]
        pr_body = (self.pr_data.get("body", "") or "")[:5000]
        input_prompt = get_single_agent_prompt(pr_title, pr_body)

        started_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        retry_events: list[dict] = []
        last_error = None
        for attempt in range(3):
            try:
                result = await Runner.run(agent, input_prompt, max_turns=1000)
                break
            except Exception as e:
                last_error = e
                waited = float(2 ** attempt)
                retry_events.append({
                    "attempt": attempt,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "timestamp": datetime.now().isoformat(),
                    "waited_seconds": waited,
                })
                if attempt < 2:
                    await asyncio.sleep(waited)
        else:
            raise last_error

        duration = round(time.perf_counter() - t0, 4)
        completed_at = datetime.now().isoformat()

        usage = result.context_wrapper.usage
        token_usage = AgentTokenUsage(
            agent_name="single_agent",
            requests=usage.requests,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

        if self.verbose:
            print(f"\n{Fore.GREEN}✅ Single Agent completed{Style.RESET_ALL}")

        final_output: PlannerOutput = result.final_output
        output_dict = final_output.model_dump()

        session = AgentSession(
            name="single_agent",
            phase=1,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            system_prompt="",
            system_prompt_chars=0,
            input_prompt=input_prompt,
            input_prompt_chars=len(input_prompt),
            token_usage=token_usage,
            retry_count=len(retry_events),
            retry_events=[RetryEvent(**e) for e in retry_events],
            tool_calls=[ToolCall(**tc) for tc in tool_call_log],
            output=output_dict,
        )

        return final_output, session

    def _generate_output_json(self, planner: PlannerOutput) -> dict:
        pr_num = self.pr_data.get("pull_request_number") or self.pr_data.get("number", 0)
        return {
            "pr_number": pr_num,
            "repository": self.pr_data.get("repository", "unknown/unknown"),
            "title": self.pr_data.get("title", ""),
            "body": self.pr_data.get("body", "") or "",
            "extraction_metadata": {
                "extracted_at": datetime.now().isoformat(),
                "extractor_version": "1.0.0-single-agent",
                "success": True,
                "error_message": None,
            },
            "files_modified": [],   # single agent skips the intermediate AnalysisOutput
            "step_plan": {
                "summary": planner.step_plan.summary,
                "steps": [
                    {
                        "operation": step.operation,
                        "file_to_modify": step.file_to_modify,
                        "function_to_modify": step.function_to_modify,
                        "reason": step.reason,
                        "side_effects": step.side_effects,
                    }
                    for step in planner.step_plan.steps
                ],
            },
        }

    async def run(self) -> tuple[dict, SessionLog]:
        if self.verbose:
            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"{Fore.CYAN}🚀 Single Agent Runner (ablation baseline)")
            print(f"{Fore.CYAN}{'='*80}")
            print(f"{Fore.CYAN}📁 PR Directory: {self.pr_dir}")
            print(f"{Fore.CYAN}🤖 Model: {self.model_name}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")

        pr_num = self.pr_data.get("pull_request_number") or self.pr_data.get("number", 0)
        pipeline_started_at = datetime.now().isoformat()
        t0_pipeline = time.perf_counter()

        planner, agent_session = await self._run_single_agent()

        pipeline_duration = round(time.perf_counter() - t0_pipeline, 4)
        pipeline_completed_at = datetime.now().isoformat()

        output = self._generate_output_json(planner)

        token_summary = {
            "total_requests": agent_session.token_usage.requests,
            "total_input_tokens": agent_session.token_usage.input_tokens,
            "total_output_tokens": agent_session.token_usage.output_tokens,
            "total_tokens": agent_session.token_usage.total_tokens,
        }

        compact_ts = pipeline_started_at[:19].replace("-", "").replace("T", "_").replace(":", "")
        session_id = f"pr{pr_num}_{compact_ts}_sa"

        session_log = SessionLog(
            session_id=session_id,
            pr_number=pr_num,
            repository=self.pr_data.get("repository", "unknown/unknown"),
            model=self.model_name,
            extractor_version="1.0.0-single-agent",
            started_at=pipeline_started_at,
            completed_at=pipeline_completed_at,
            duration_seconds=pipeline_duration,
            success=True,
            error=None,
            context=SessionContext(
                pr_title=self.pr_data.get("title", ""),
                pr_body=self.pr_data.get("body", "") or "",
                masca_available=self.masca_path.exists(),
                masca_chars=0,          # masca not injected
                call_graph_available=(self.context_output_path / "call_graph.json").exists(),
                context_files_available=(self.context_output_path / "context_files").exists(),
                ablation=False,
            ),
            agents=[agent_session],
            token_summary=token_summary,
        )

        if self.verbose:
            print(f"\n{Fore.GREEN}{'='*80}")
            print(f"{Fore.GREEN}✅ Pipeline completed!")
            print(f"{Fore.GREEN}   Steps generated: {len(planner.step_plan.steps)}")
            print(f"{Fore.GREEN}   Total tokens:    {token_summary['total_tokens']}")
            print(f"{Fore.GREEN}   Pipeline time:   {pipeline_duration}s")
            print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}")

        return output, session_log

    def run_sync(self) -> tuple[dict, SessionLog]:
        return run_async_safely(self.run())

    def save_output(self) -> tuple[str, str, str]:
        """
        Run the pipeline and save outputs to pr_dir/evals/single_agent_turn/.

        Returns:
            Tuple of (predicted_plan_path, token_usage_path, session_log_path)
        """
        output, session_log = self.run_sync()

        out_dir = self.pr_dir / self._eval_subdir
        out_dir.mkdir(parents=True, exist_ok=True)

        predicted_path = out_dir / "predicted_plan.json"
        with open(predicted_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        token_path = out_dir / "token_usage.json"
        token_report = TokenUsageReport(
            pr_number=session_log.pr_number,
            repository=session_log.repository,
            timestamp=session_log.started_at,
            model_name=session_log.model,
            agents=[s.token_usage for s in session_log.agents],
            total_requests=session_log.token_summary["total_requests"],
            total_input_tokens=session_log.token_summary["total_input_tokens"],
            total_output_tokens=session_log.token_summary["total_output_tokens"],
            total_tokens=session_log.token_summary["total_tokens"],
            duration_seconds=session_log.duration_seconds,
        )
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(token_report.model_dump(), f, indent=2, ensure_ascii=False)

        session_path = out_dir / "session_log.json"
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session_log.model_dump(), f, indent=2, ensure_ascii=False)

        # Copy ground_truth.json so the evaluator can find it alongside predicted_plan.json
        gt_src = self.pr_dir / "ground_truth.json"
        if gt_src.exists():
            shutil.copy2(gt_src, out_dir / "ground_truth.json")

        # Mirror results into the consolidated eval folder (e.g. single_agent_evals/single_agent_turn)
        # Layout: eval_dir/<owner_repo>/<pr_NUMBER>/{predicted_plan, token_usage, session_log,
        #                                             ground_truth, data}.json
        if self.eval_dir:
            # Infer owner_repo and pr_NUMBER from the PR directory path
            pr_name = self.pr_dir.name          # e.g. "pr_383"
            repo_name = self.pr_dir.parent.name  # e.g. "THUDM_CogVideo"
            consolidated = self.eval_dir / repo_name / pr_name
            consolidated.mkdir(parents=True, exist_ok=True)

            for fname in ["predicted_plan.json", "token_usage.json", "session_log.json", "ground_truth.json"]:
                src = out_dir / fname
                if src.exists():
                    shutil.copy2(src, consolidated / fname)

            # Also copy data.json from the PR root (metadata, matches gpt_5-2_evals layout)
            data_src = self.pr_dir / "data.json"
            if data_src.exists():
                shutil.copy2(data_src, consolidated / "data.json")

            if self.verbose:
                print(f"{Fore.GREEN}📁 Consolidated:   {consolidated}{Style.RESET_ALL}")

        if self.verbose:
            print(f"\n{Fore.GREEN}💾 Predicted plan: {predicted_path}")
            print(f"{Fore.GREEN}📊 Token usage:    {token_path}")
            print(f"{Fore.GREEN}📋 Session log:    {session_path}{Style.RESET_ALL}")

        return str(predicted_path), str(token_path), str(session_path)


# =============================================================================
# CLI

def main():
    parser = argparse.ArgumentParser(
        description="Single Agent Runner -- ablation baseline for the two-agent pipeline."
    )
    parser.add_argument("pr_dir", help="Path to the PR directory")
    parser.add_argument("-m", "--model", default=None, help="OpenAI model override")
    parser.add_argument("-q", "--quiet", action="store_true", help="Minimal output")

    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print(f"{Fore.RED}OPENAI_API_KEY not found in .env file{Style.RESET_ALL}")
        raise SystemExit(1)

    planner = SingleAgentPlanner(
        pr_dir=args.pr_dir,
        model_name=args.model,
        verbose=not args.quiet,
    )
    planner.save_output()


if __name__ == "__main__":
    main()
