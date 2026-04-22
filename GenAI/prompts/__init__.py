"""
GenAI Prompts Module

Centralized repository for all LLM system prompts used across the project.
Each prompt is stored as a constant or template function for easy maintenance.
"""

from .step_planner import STEP_PLANNER_PROMPT, get_step_planner_prompt
from .analysis_agent import ANALYSIS_AGENT_PROMPT, get_analysis_agent_prompt
from .context_planner import CONTEXT_PLANNER_PROMPT
from .masca import MASCA_PROMPT, get_masca_prompt
from .single_agent import get_single_agent_prompt

__all__ = [
    # Step Planner
    "STEP_PLANNER_PROMPT",
    "get_step_planner_prompt",
    # Analysis Agent
    "ANALYSIS_AGENT_PROMPT",
    "get_analysis_agent_prompt",
    # Context Planner
    "CONTEXT_PLANNER_PROMPT",
    # MASCA
    "MASCA_PROMPT",
    "get_masca_prompt",
    # Single Agent (ablation baseline)
    "get_single_agent_prompt",
]
