# GenAI Architecture

## Overview

`GenAI` is organized as a PR-planning pipeline around one core orchestrator, `PRStepPlanner`. The module separates discovery from planning:

- Phase 1 decides what must change.
- Phase 2 decides how to change it.
- Supporting modules handle context generation, batch execution, evaluation, configuration, and safe file access.

This keeps the planning pipeline modular: orchestration is in one place, agent tools are isolated, and evaluation is independent from generation.

## System Architecture

```mermaid
flowchart TB
    subgraph Inputs
        A[data.json]
        B[base_project/]
        C[context_output/<br/>masca_analysis.md<br/>call_graph.json<br/>context_files/]
        D[agents_config.toml]
    end

    subgraph Core
        E[config_loader.py]
        F[PRStepPlanner]
        G[Analysis Agent]
        H[Context Planner Agent]
        I[tools.py sandboxed tools]
        J[utils.py]
    end

    subgraph Outputs
        K[predicted_plan.json]
        L[token_usage.json]
        M[session_log.json]
    end

    subgraph Secondary Flows
        N[batch_predict.py]
        O[single_agent_runner.py]
        P[masca_runner.py]
        Q[evaluate_predictions.py]
        R[evaluation_score.json / batch report]
    end

    D --> E --> F
    A --> F
    B --> F
    C --> F
    J --> F
    F --> G
    G --> I
    G --> H
    H --> I
    H --> K
    F --> L
    F --> M
    N --> F
    O --> I
    P --> C
    K --> Q
    Q --> R
```

## Responsibilities By Module

- `pr_step_planner.py`: the primary runtime. It validates the PR directory, loads PR metadata, resolves MASCA context, runs both agents, and writes normalized outputs.
- `tools.py`: shared low-level file and directory tools. `pr_step_planner.py` wraps them into sandboxed agent tools so agents only read allowed paths.
- `config_loader.py`: loads `agents_config.toml`, validates it with Pydantic, and caches the result.
- `batch_predict.py`: runs the planner over many `pr_*` directories, sequentially or with a thread pool.
- `single_agent_runner.py`: baseline path for experiments that remove the two-phase split.
- `masca_runner.py`: generates project-level context from README content plus a directory tree.
- `evaluate_predictions.py`: post-run evaluation layer. It is intentionally decoupled from generation so prediction and scoring can evolve independently.
- `utils.py`: provides `run_async_safely`, which lets the module run async agent workflows from CLI-style synchronous entry points.

## Two-Agent Runtime

The main pipeline is intentionally staged:

1. `PRStepPlanner` loads `data.json`, `base_project/`, optional MASCA analysis, and model settings.
2. The Analysis Agent receives the PR title/body and MASCA context.
3. The Analysis Agent uses sandboxed base-project tools to inspect code and returns structured `AnalysisOutput`.
4. The Context Planner Agent receives that structured output.
5. The Context Planner Agent uses context files and the call graph to expand targets into a `StepPlan`.
6. The planner persists the final prediction, token summary, and full session log.

```mermaid
sequenceDiagram
    participant PR as PRStepPlanner
    participant AA as Analysis Agent
    participant BT as Base-project tools
    participant CP as Context Planner Agent
    participant CT as Context tools

    PR->>AA: PR title/body + MASCA context
    AA->>BT: list/read files in base_project
    BT-->>AA: file summaries or raw content
    AA-->>PR: AnalysisOutput
    PR->>CP: files/functions to modify + analysis summary
    CP->>CT: read context files / call graph
    CT-->>CP: dependency context
    CP-->>PR: PlannerOutput(step_plan)
    PR->>PR: write predicted_plan.json, token_usage.json, session_log.json
```

## State Transitions

```mermaid
stateDiagram-v2
    [*] --> ValidateInputs
    ValidateInputs --> LoadConfig
    LoadConfig --> LoadPRData
    LoadPRData --> LoadMASCA
    LoadMASCA --> RunAnalysisAgent
    RunAnalysisAgent --> RunContextPlanner
    RunContextPlanner --> BuildOutputJson
    BuildOutputJson --> WriteArtifacts
    WriteArtifacts --> Completed
    Completed --> [*]

    ValidateInputs --> Failed
    LoadConfig --> Failed
    LoadPRData --> Failed
    LoadMASCA --> Failed
    RunAnalysisAgent --> Failed
    RunContextPlanner --> Failed
    BuildOutputJson --> Failed
    WriteArtifacts --> Failed
    Failed --> [*]
```

## Data Boundaries

The module has three important data contracts:

- `AnalysisOutput`: intermediate contract from phase 1, containing files, functions, and reasoning.
- `PlannerOutput`: final typed plan contract, centered on `StepPlan`.
- `SessionLog`: observability contract, capturing prompts, tool calls, retries, timings, and token usage.

This separation is useful because generation quality, evaluation logic, and dashboards can change without collapsing into one format.

## Evaluation Architecture

Evaluation is not part of the planning runtime. It is a separate pass over saved artifacts:

- prediction input: `predicted_plan.json`
- reference input: `ground_truth.json`
- outputs: `evaluation_score.json` or aggregated batch reports

The evaluator mixes exact and semantic checks:

- deterministic file matching
- deterministic function matching
- step-count and target-coverage analysis
- optional embedding-based semantic similarity

That design makes the scoring path reproducible for structure-level metrics while still allowing a softer semantic comparison for natural-language plan quality.

## How This Module Is Used In The Project

Within the full repository, `GenAI/` is the prediction layer between preprocessing and scoring:

- Upstream, `context_retrieving/` prepares `call_graph.json`, `context_files/*`, `project_tree.txt`, and optional MASCA output that the planners use as structured context.
- At the schema boundary, `GenAI/pr_step_planner.py` and `GenAI/single_agent_runner.py` import `Step` and `StepPlan` from `evaluation.models`, which keeps predicted plans aligned with the evaluation format.
- At the interface layer, `cli/handlers/prediction.py` calls `GenAI.batch_predict.run_batch(...)` for interactive batch inference, and `cli/handlers/repository.py` reuses `GenAI.masca_runner` when building repository summaries.
- Downstream, `GenAI/evaluate_predictions.py` compares `predicted_plan.json` to `ground_truth.json` and writes `evaluation_score.json`.
- Finally, `dashboard/server.py` consumes `predicted_plan.json`, `evaluation_score.json`, `token_usage.json`, and `session_log.json` to power result browsing and drill-down views.
