"""
Evaluate Predictions - Compare predicted_plan.json with ground_truth.json
=========================================================================

Computed metrics:
1. File Identification: Precision, Recall, F1 on modified files
2. Function Identification: Precision, Recall, F1 on modified functions
3. Step Plan Analysis: Step count comparison and target coverage
4. Semantic Similarity: Semantic similarity using OpenAI embeddings

Usage:
    # Single PR
    python -m GenAI.evaluate_predictions PR4Code/.../pr_123/

    # Batch evaluation
    python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py/ --batch

    # With semantic analysis (requires OpenAI API key)
    python -m GenAI.evaluate_predictions PR4Code/.../pr_123/ --semantic

    # Save report
    python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py/ --batch --report eval_report.json

Author: PR4Code Project
"""

import os
import sys
import json
import argparse
import numpy as np
from pathlib import Path
from typing import Optional, List, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime

from dotenv import load_dotenv
from colorama import Fore, Style, init

init(autoreset=True)
load_dotenv()

# OpenAI client (lazy loading)
_openai_client = None

def get_openai_client():
    """Lazy loading of the OpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    return _openai_client


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MetricScore:
    """Score for a single metric (precision, recall, F1)."""
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0

    predicted_count: int = 0
    actual_count: int = 0
    correct_count: int = 0


@dataclass
class StepAnalysis:
    """Step plan analysis."""
    predicted_steps: int = 0
    actual_steps: int = 0
    step_diff: int = 0

    # How many predicted targets match with actual files/functions
    target_coverage: float = 0.0
    targets_matched: int = 0
    targets_total: int = 0


@dataclass
class SemanticScore:
    """Semantic similarity score using embeddings (summary and step NL only)."""
    # Similarity between predicted and actual summary
    summary_similarity: float = 0.0

    # Average similarity between steps (best match for each predicted step)
    avg_step_similarity: float = 0.0

    # Step match details (list of dict: pred_idx, gt_idx, similarity)
    step_matches: List[dict] = field(default_factory=list)

    # Overall score (weighted average: 30% summary, 70% steps)
    overall_semantic_score: float = 0.0

    # Flag indicating if analysis was performed
    computed: bool = False
    error: Optional[str] = None


@dataclass
class PRScore:
    """Complete score for a single PR."""
    pr_dir: str
    pr_number: int = 0
    repository: str = ""

    files: MetricScore = field(default_factory=MetricScore)
    functions: MetricScore = field(default_factory=MetricScore)
    steps: StepAnalysis = field(default_factory=StepAnalysis)
    semantic: SemanticScore = field(default_factory=SemanticScore)

    has_prediction: bool = False
    has_ground_truth: bool = False
    error: Optional[str] = None


@dataclass
class BatchReport:
    """Aggregated report for batch evaluation."""
    timestamp: str = ""
    total_prs: int = 0
    evaluated_prs: int = 0
    skipped_prs: int = 0

    # Aggregated averages
    avg_file_precision: float = 0.0
    avg_file_recall: float = 0.0
    avg_file_f1: float = 0.0

    avg_function_precision: float = 0.0
    avg_function_recall: float = 0.0
    avg_function_f1: float = 0.0

    avg_step_diff: float = 0.0
    std_step_diff: Optional[float] = None   # None when < 2 PRs evaluated
    avg_target_coverage: float = 0.0

    # Semantic metrics (if computed)
    avg_semantic_score: float = 0.0
    avg_summary_similarity: float = 0.0
    avg_step_similarity: float = 0.0
    semantic_evaluated: int = 0

    # Details per PR
    pr_scores: List[dict] = field(default_factory=list)


# =============================================================================
# EVALUATION FUNCTIONS
# =============================================================================

def _file_match_quality(pred_file: str, gt_file: str) -> int:
    """
    Return a match quality score for two file path strings.

    3 = exact match
    2 = suffix/prefix match (one path is a trailing component of the other,
        e.g. 'models/openai.py' vs 'pydantic_ai_slim/models/openai.py')
    1 = basename match (last path component identical,
        handles 'base_project/metric.py' vs 'lm_eval/.../metric.py')
    0 = no match
    """
    if pred_file == gt_file:
        return 3
    if gt_file.endswith(pred_file) or pred_file.endswith(gt_file):
        return 2
    if Path(pred_file).name == Path(gt_file).name:
        return 1
    return 0


def calculate_file_metrics(predicted: Set[str], actual: Set[str]) -> MetricScore:
    """
    Calculate precision, recall, and F1 for file identification.

    Uses path-aware bipartite matching: exact match is preferred, then
    suffix/prefix matching (e.g. the model emits 'models/openai.py' while
    the GT has the full repo path), then basename matching (handles
    'base_project/metric.py' vs 'lm_eval/.../metric.py').
    Each predicted file and each GT file can be matched at most once.

    Precision = TP / predicted  |  Recall = TP / actual  |  F1 = harmonic mean
    """
    if not predicted and not actual:
        return MetricScore()

    candidates = sorted(
        [
            (q, pred, gt_file)
            for pred in predicted
            for gt_file in actual
            if (q := _file_match_quality(pred, gt_file)) > 0
        ],
        reverse=True,
    )

    matched_pred: Set[str] = set()
    matched_gt: Set[str] = set()
    correct = 0
    for _, pred, gt_file in candidates:
        if pred in matched_pred or gt_file in matched_gt:
            continue
        matched_pred.add(pred)
        matched_gt.add(gt_file)
        correct += 1

    precision = correct / len(predicted) if predicted else 0.0
    recall = correct / len(actual) if actual else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return MetricScore(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        predicted_count=len(predicted),
        actual_count=len(actual),
        correct_count=correct,
    )


def extract_files_from_ground_truth(gt: dict) -> Set[str]:
    """Extract modified file names from ground truth."""
    files = set()
    for f in gt.get("files_modified", []):
        filename = f.get("filename", "")
        if filename:
            files.add(filename)
    return files


def extract_files_from_prediction(pred: dict) -> Set[str]:
    """
    Extract files to modify from prediction steps.
    Reads step_plan.steps[].file_to_modify
    """
    files = set()
    steps = pred.get("step_plan", {}).get("steps", [])
    for step in steps:
        file_to_modify = step.get("file_to_modify", "")
        if file_to_modify:
            files.add(file_to_modify)
    return files


def _function_match_quality(pred_func: str, gt_short: str, gt_full: str) -> int:
    """
    Return a match quality score for two function name strings.

    3 = exact match against the GT fully-qualified name (e.g. 'Class._get_event_iterator')
    2 = exact match against the GT short name (e.g. '_get_event_iterator')
    1 = last component of pred equals GT short name
        (handles 'OpenAIStreamedResponse._get_event_iterator' vs '_get_event_iterator')
    0 = no match
    """
    if not pred_func:
        return 0
    if gt_full and pred_func == gt_full:
        return 3
    if gt_short and pred_func == gt_short:
        return 2
    pred_short = pred_func.split(".")[-1]
    if gt_short and pred_short == gt_short:
        return 1
    return 0


def extract_function_refs_from_ground_truth(gt: dict) -> List[dict]:
    """
    Return one dict per modified function with 'short' and 'full' name variants.
    Reads files_modified[].functions_modified[] from the ground truth.

    The resulting list is used by calculate_function_metrics for bipartite
    matching against predicted function names, supporting both short names
    (function_name) and fully-qualified names (full_name, e.g. 'Class.method').
    """
    refs = []
    for f in gt.get("files_modified", []):
        for func in f.get("functions_modified", []):
            refs.append({
                "short": func.get("function_name", ""),
                "full": func.get("full_name", ""),
            })
    return refs


def calculate_function_metrics(predicted: Set[str], gt_refs: List[dict]) -> MetricScore:
    """
    Calculate precision, recall, and F1 for function identification.

    Uses name-variant-aware bipartite matching: a prediction is correct if it
    matches a GT function's fully-qualified name, its short name, or its short
    name after stripping the predicted class prefix (e.g. 'Class.method' → 'method').
    Each predicted name and each GT function can be matched at most once.

    gt_refs is produced by extract_function_refs_from_ground_truth().

    Precision = TP / predicted  |  Recall = TP / actual  |  F1 = harmonic mean
    """
    if not predicted and not gt_refs:
        return MetricScore()

    candidates = sorted(
        [
            (q, pred, i)
            for pred in predicted
            for i, ref in enumerate(gt_refs)
            if (q := _function_match_quality(pred, ref["short"], ref["full"])) > 0
        ],
        reverse=True,
    )

    matched_pred: Set[str] = set()
    matched_gt_idx: Set[int] = set()
    correct = 0
    for _, pred, gt_idx in candidates:
        if pred in matched_pred or gt_idx in matched_gt_idx:
            continue
        matched_pred.add(pred)
        matched_gt_idx.add(gt_idx)
        correct += 1

    actual_count = len(gt_refs)
    pred_count = len(predicted)
    precision = correct / pred_count if pred_count else 0.0
    recall = correct / actual_count if actual_count else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return MetricScore(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        predicted_count=pred_count,
        actual_count=actual_count,
        correct_count=correct,
    )


def extract_functions_from_prediction(pred: dict) -> Set[str]:
    """
    Extract functions to modify from prediction steps.
    Reads step_plan.steps[].function_to_modify (ignores null values)
    """
    functions = set()
    steps = pred.get("step_plan", {}).get("steps", [])
    for step in steps:
        func_to_modify = step.get("function_to_modify")
        if func_to_modify:  # Ignore None/null
            functions.add(func_to_modify)
    return functions


def analyze_steps(pred: dict, gt: dict) -> StepAnalysis:
    """
    Analyze the step plan.

    Compares:
    - Number of predicted vs actual steps
    - How many file_to_modify/function_to_modify match with ground truth

    actual_steps is derived deterministically from files_modified:
      one step per function modified; if a file has no functions listed,
      it counts as one step. This avoids using the AI-generated step_plan
      stored in ground_truth.json.
    """
    pred_steps = pred.get("step_plan", {}).get("steps", [])

    pred_count = len(pred_steps) if pred_steps else 0

    # Deterministic actual step count from the raw diff data
    gt_count = 0
    for f in gt.get("files_modified", []):
        funcs = f.get("functions_modified", [])
        gt_count += len(funcs) if funcs else 1

    # Extract actual targets from ground truth (deterministic)
    gt_files = extract_files_from_ground_truth(gt)
    gt_func_refs = extract_function_refs_from_ground_truth(gt)

    # Count how many predicted steps match with actual files/functions
    matched = 0
    total = 0

    for step in pred_steps:
        file_to_modify = step.get("file_to_modify", "")
        func_to_modify = step.get("function_to_modify")

        if file_to_modify:
            total += 1
            step_matched = False

            # Path-aware file match (exact, then suffix/prefix, then basename)
            if any(_file_match_quality(file_to_modify, gt_file) > 0 for gt_file in gt_files):
                step_matched = True

            # Function name match (full name, short name, or last component)
            if func_to_modify and gt_func_refs:
                if any(
                    _function_match_quality(func_to_modify, r["short"], r["full"]) > 0
                    for r in gt_func_refs
                ):
                    step_matched = True

            if step_matched:
                matched += 1

    coverage = matched / total if total > 0 else 0.0

    return StepAnalysis(
        predicted_steps=pred_count,
        actual_steps=gt_count,
        step_diff=pred_count - gt_count,
        target_coverage=round(coverage, 4),
        targets_matched=matched,
        targets_total=total
    )


# =============================================================================
# SEMANTIC SIMILARITY FUNCTIONS
# =============================================================================

def get_embedding(text: str, model: str = "text-embedding-3-large") -> Optional[List[float]]:
    """
    Get the embedding of a text using OpenAI API.

    Args:
        text: Text to convert to embedding
        model: Embedding model. text-embedding-3-large gives higher accuracy;
               text-embedding-3-small is faster and cheaper.

    Returns:
        List of floats representing the embedding, or None on error
    """
    if not text or not text.strip():
        return None

    try:
        client = get_openai_client()
        response = client.embeddings.create(
            input=text.strip(),
            model=model
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"{Fore.RED}   ⚠️ Embedding error: {e}{Style.RESET_ALL}")
        return None


def get_embeddings_batch(texts: List[str], model: str = "text-embedding-3-large") -> List[Optional[List[float]]]:
    """
    Get embeddings for a list of texts in a single batch API call.

    Args:
        texts: List of texts
        model: Embedding model. text-embedding-3-large gives higher accuracy;
               text-embedding-3-small is faster and cheaper.

    Returns:
        List of embeddings (None for empty texts/errors)
    """
    # Filter empty texts while keeping indices
    valid_texts = []
    valid_indices = []
    for i, text in enumerate(texts):
        if text and text.strip():
            valid_texts.append(text.strip())
            valid_indices.append(i)

    if not valid_texts:
        return [None] * len(texts)

    try:
        client = get_openai_client()
        response = client.embeddings.create(
            input=valid_texts,
            model=model
        )

        # Rebuild list with None for empty texts
        result = [None] * len(texts)
        for i, emb_data in enumerate(response.data):
            original_idx = valid_indices[i]
            result[original_idx] = emb_data.embedding

        return result

    except Exception as e:
        print(f"{Fore.RED}   ⚠️ Batch embedding error: {e}{Style.RESET_ALL}")
        return [None] * len(texts)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate the cosine similarity between two vectors.

    Cosine Similarity = (A · B) / (||A|| * ||B||)

    Range: [-1, 1] where 1 = identical, 0 = orthogonal, -1 = opposite
    For text, typically range [0, 1]
    """
    if vec1 is None or vec2 is None:
        return 0.0

    a = np.array(vec1)
    b = np.array(vec2)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def step_to_text(step: dict) -> str:
    """
    Convert a step to text for embedding.
    file_to_modify is intentionally excluded — it is already measured
    exactly by the F1 metrics and would contaminate the semantic score.
    """
    parts = []
    if step.get("operation"):
        parts.append(f"Operation: {step['operation']}")
    if step.get("function_to_modify"):
        parts.append(f"Function: {step['function_to_modify']}")
    if step.get("reason"):
        parts.append(f"Reason: {step['reason']}")
    if step.get("side_effects"):
        parts.append(f"Side effects: {step['side_effects']}")
    return " | ".join(parts)


def compute_semantic_similarity(pred: dict, gt: dict) -> SemanticScore:
    """
    Calculate semantic similarity between prediction and ground truth.

    Computes embeddings only for:
    1. Summary: the plan summary in natural language
    2. Steps: the full text of each step in natural language

    Overall score = 30% summary + 70% steps
    """
    score = SemanticScore()

    try:
        pred_plan = pred.get("step_plan", {}) or {}
        gt_plan = gt.get("step_plan", {}) or {}

        pred_steps = pred_plan.get("steps", []) or []
        gt_steps = gt_plan.get("steps", []) or []

        pred_summary = pred_plan.get("summary", "") or ""
        gt_summary = gt_plan.get("summary", "") or ""

        # Skip if there's no data to compare
        if not pred_steps and not gt_steps and not pred_summary and not gt_summary:
            score.error = "No data to compare"
            return score

        print(f"{Fore.CYAN}   🧠 Computing embeddings (summary + steps NL)...{Style.RESET_ALL}")

        # 1. Summary similarity
        if pred_summary and gt_summary:
            emb_pred_summary = get_embedding(pred_summary)
            emb_gt_summary = get_embedding(gt_summary)
            score.summary_similarity = round(cosine_similarity(emb_pred_summary, emb_gt_summary), 4)

        # 2. Step embeddings — greedy exclusive matching
        if pred_steps and gt_steps:
            pred_step_texts = [step_to_text(s) for s in pred_steps]
            gt_step_texts = [step_to_text(s) for s in gt_steps]

            all_texts = pred_step_texts + gt_step_texts
            all_embeddings = get_embeddings_batch(all_texts)

            pred_embeddings = all_embeddings[:len(pred_steps)]
            gt_embeddings = all_embeddings[len(pred_steps):]

            # Build full score matrix (N_pred x N_gt)
            score_matrix = []
            for pred_emb in pred_embeddings:
                row = []
                for gt_emb in gt_embeddings:
                    if pred_emb is None or gt_emb is None:
                        row.append(0.0)
                    else:
                        row.append(cosine_similarity(pred_emb, gt_emb))
                score_matrix.append(row)

            # Greedy exclusive assignment: highest score pair first,
            # each pred step and GT step can only be matched once
            all_pairs = sorted(
                [
                    (score_matrix[i][j], i, j)
                    for i in range(len(pred_steps))
                    for j in range(len(gt_steps))
                ],
                reverse=True,
            )

            def _truncate(text: str) -> str:
                return text[:100] + "..." if len(text) > 100 else text

            assigned_pred: set = set()
            assigned_gt: set = set()
            step_matches = []
            matched_similarities = []

            for sim, i, j in all_pairs:
                if i in assigned_pred or j in assigned_gt:
                    continue
                assigned_pred.add(i)
                assigned_gt.add(j)
                matched_similarities.append(sim)
                step_matches.append({
                    "pred_idx": i,
                    "pred_text": _truncate(pred_step_texts[i]),
                    "gt_idx": j,
                    "gt_text": _truncate(gt_step_texts[j]),
                    "similarity": round(sim, 4),
                })

            # Unmatched predicted steps contribute 0 to the average
            unmatched_count = len(pred_steps) - len(assigned_pred)
            all_similarities = matched_similarities + [0.0] * unmatched_count

            if all_similarities:
                score.avg_step_similarity = round(
                    sum(all_similarities) / len(all_similarities), 4
                )

            score.step_matches = sorted(step_matches, key=lambda m: m["pred_idx"])

        # 3. Overall semantic score (30% summary, 70% steps)
        overall = 0.30 * score.summary_similarity + 0.70 * score.avg_step_similarity
        score.overall_semantic_score = round(overall, 4)
        score.computed = True

        print(f"{Fore.GREEN}   ✅ Semantic analysis completed{Style.RESET_ALL}")

    except Exception as e:
        score.error = str(e)
        print(f"{Fore.RED}   ❌ Semantic analysis error: {e}{Style.RESET_ALL}")

    return score


def _persist_score(score: PRScore, pr_dir: Path) -> None:
    """
    Write evaluation_score.json into the PR directory.
    Called on every exit path — including error states — so the dashboard
    always has a file to read, even if evaluation failed.
    I/O errors are logged to stderr and do not propagate.
    """
    try:
        out_path = pr_dir / "evaluation_score.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                {"evaluated_at": datetime.now().isoformat(), **asdict(score)},
                f, indent=2, ensure_ascii=False,
            )
    except Exception as e:
        print(f"{Fore.RED}   ⚠️ Could not save evaluation_score.json: {e}{Style.RESET_ALL}",
              file=sys.stderr)


def evaluate_single_pr(pr_dir: Path, compute_semantic: bool = False) -> PRScore:
    """
    Evaluate a single PR by comparing predicted_plan.json with ground_truth.json.
    Always saves the result to pr_dir/evaluation_score.json, including error states.
    """
    score = PRScore(pr_dir=str(pr_dir))

    pred_path = pr_dir / "predicted_plan.json"
    gt_path = pr_dir / "ground_truth.json"

    # Check file existence
    if not pred_path.exists():
        score.error = "predicted_plan.json not found"
        _persist_score(score, pr_dir)
        return score

    if not gt_path.exists():
        score.error = "ground_truth.json not found"
        _persist_score(score, pr_dir)
        return score

    # Load files
    try:
        with open(pred_path, 'r', encoding='utf-8') as f:
            pred = json.load(f)
        score.has_prediction = True
    except Exception as e:
        score.error = f"Error reading predicted_plan.json: {e}"
        _persist_score(score, pr_dir)
        return score

    try:
        with open(gt_path, 'r', encoding='utf-8') as f:
            gt = json.load(f)
        score.has_ground_truth = True
    except Exception as e:
        score.error = f"Error reading ground_truth.json: {e}"
        _persist_score(score, pr_dir)
        return score

    # Metadata
    score.pr_number = gt.get("pr_number", 0)
    score.repository = gt.get("repository", "")

    # Evaluate files
    pred_files = extract_files_from_prediction(pred)
    gt_files = extract_files_from_ground_truth(gt)
    score.files = calculate_file_metrics(pred_files, gt_files)

    # Evaluate functions
    pred_functions = extract_functions_from_prediction(pred)
    gt_func_refs = extract_function_refs_from_ground_truth(gt)
    score.functions = calculate_function_metrics(pred_functions, gt_func_refs)

    # Analyze steps
    score.steps = analyze_steps(pred, gt)

    # Semantic analysis (optional)
    if compute_semantic:
        score.semantic = compute_semantic_similarity(pred, gt)

    _persist_score(score, pr_dir)
    return score


def print_pr_score(score: PRScore, verbose: bool = True):
    """Print the evaluation result of a PR."""
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}📊 PR: {score.repository} #{score.pr_number}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")

    if score.error:
        print(f"{Fore.RED}❌ Error: {score.error}{Style.RESET_ALL}")
        return

    # File metrics
    f = score.files
    print(f"\n{Fore.YELLOW}📁 FILE IDENTIFICATION:{Style.RESET_ALL}")
    print(f"   Predicted: {f.predicted_count} | Actual: {f.actual_count} | Correct: {f.correct_count}")
    print(f"   Precision: {f.precision:.2%} | Recall: {f.recall:.2%} | F1: {f.f1:.2%}")

    # Function metrics
    fn = score.functions
    print(f"\n{Fore.YELLOW}🔧 FUNCTION IDENTIFICATION:{Style.RESET_ALL}")
    print(f"   Predicted: {fn.predicted_count} | Actual: {fn.actual_count} | Correct: {fn.correct_count}")
    print(f"   Precision: {fn.precision:.2%} | Recall: {fn.recall:.2%} | F1: {fn.f1:.2%}")

    # Step analysis
    s = score.steps
    print(f"\n{Fore.YELLOW}📋 STEP PLAN ANALYSIS:{Style.RESET_ALL}")
    print(f"   Predicted steps: {s.predicted_steps} | Actual steps: {s.actual_steps} | Diff: {s.step_diff:+d}")
    print(f"   Target coverage: {s.target_coverage:.2%} ({s.targets_matched}/{s.targets_total} targets match)")

    # Semantic analysis (if computed)
    sem = score.semantic
    if sem.computed:
        print(f"\n{Fore.YELLOW}🧠 SEMANTIC SIMILARITY (NL):{Style.RESET_ALL}")
        print(f"   Summary similarity: {sem.summary_similarity:.2%}")
        print(f"   Avg step similarity: {sem.avg_step_similarity:.2%}")
        print(f"   {Fore.CYAN}Overall (30% summary + 70% steps): {sem.overall_semantic_score:.2%}{Style.RESET_ALL}")

        if verbose and sem.step_matches:
            print(f"\n   Step matches:")
            for match in sem.step_matches[:5]:  # Show max 5 matches
                print(f"   - Pred[{match['pred_idx']}] → GT[{match['gt_idx']}]: {match['similarity']:.2%}")
            if len(sem.step_matches) > 5:
                print(f"   ... and {len(sem.step_matches) - 5} more steps")
    elif sem.error:
        print(f"\n{Fore.YELLOW}🧠 SEMANTIC SIMILARITY:{Style.RESET_ALL}")
        print(f"   {Fore.RED}⚠️ {sem.error}{Style.RESET_ALL}")

    # Overall assessment
    avg_f1 = (f.f1 + fn.f1) / 2
    print(f"\n{Fore.GREEN}📈 OVERALL:{Style.RESET_ALL}")
    print(f"   Average F1 (files + functions): {avg_f1:.2%}")
    if sem.computed:
        print(f"   Semantic score: {sem.overall_semantic_score:.2%}")
        combined = (avg_f1 + sem.overall_semantic_score) / 2
        print(f"   Combined score (F1 + Semantic): {combined:.2%}")

    if avg_f1 >= 0.7:
        print(f"   {Fore.GREEN}✅ Good prediction{Style.RESET_ALL}")
    elif avg_f1 >= 0.4:
        print(f"   {Fore.YELLOW}⚠️ Partial prediction{Style.RESET_ALL}")
    else:
        print(f"   {Fore.RED}❌ Poor prediction{Style.RESET_ALL}")


def evaluate_batch(base_path: Path, limit: Optional[int] = None, compute_semantic: bool = False, skip_existing: bool = False) -> BatchReport:
    """
    Evaluate all PRs in a directory.

    Args:
        base_path: Base directory containing the PRs
        limit: Maximum number of PRs to evaluate
        compute_semantic: If True, also compute semantic similarity (requires API key)
    """
    report = BatchReport(timestamp=datetime.now().isoformat())

    # Find all PRs that have ground_truth.json (with or without predicted_plan.json)
    pr_dirs = sorted({
        gt_path.parent
        for gt_path in base_path.rglob("ground_truth.json")
    })

    if skip_existing:
        def _has_valid_score(d: Path) -> bool:
            p = d / "evaluation_score.json"
            if not p.exists():
                return False
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                return not data.get("error")
            except Exception:
                return False

        original_count = len(pr_dirs)
        pr_dirs = [d for d in pr_dirs if not _has_valid_score(d)]
        skipped = original_count - len(pr_dirs)
        if skipped:
            print(f"{Fore.YELLOW}⏭️  Skipping {skipped} PRs with valid evaluation_score.json{Style.RESET_ALL}")

    if limit:
        pr_dirs = pr_dirs[:limit]

    report.total_prs = len(pr_dirs)

    print(f"{Fore.CYAN}📊 Evaluating {len(pr_dirs)} PRs...{Style.RESET_ALL}")
    if compute_semantic:
        print(f"{Fore.CYAN}🧠 Semantic analysis enabled (may take some time){Style.RESET_ALL}")

    # Evaluate each PR
    scores = []
    for i, pr_dir in enumerate(pr_dirs, 1):
        pr_name = f"{pr_dir.parent.name}/{pr_dir.name}"
        print(f"\n{Fore.YELLOW}[{i}/{len(pr_dirs)}] {pr_name}{Style.RESET_ALL}")

        score = evaluate_single_pr(pr_dir, compute_semantic=compute_semantic)
        scores.append(score)

        if score.error:
            report.skipped_prs += 1
            print(f"   {Fore.RED}⚠️ {score.error}{Style.RESET_ALL}")
        else:
            report.evaluated_prs += 1
            print(f"   {Fore.GREEN}✓ F1 files: {score.files.f1:.2%} | F1 funcs: {score.functions.f1:.2%}{Style.RESET_ALL}", end="")
            if score.semantic.computed:
                print(f" | Semantic: {score.semantic.overall_semantic_score:.2%}")
            else:
                print()

    # Calculate averages (only for successfully evaluated PRs)
    valid_scores = [s for s in scores if not s.error]

    if valid_scores:
        report.avg_file_precision = sum(s.files.precision for s in valid_scores) / len(valid_scores)
        report.avg_file_recall = sum(s.files.recall for s in valid_scores) / len(valid_scores)
        report.avg_file_f1 = sum(s.files.f1 for s in valid_scores) / len(valid_scores)

        report.avg_function_precision = sum(s.functions.precision for s in valid_scores) / len(valid_scores)
        report.avg_function_recall = sum(s.functions.recall for s in valid_scores) / len(valid_scores)
        report.avg_function_f1 = sum(s.functions.f1 for s in valid_scores) / len(valid_scores)

        step_diffs = [s.steps.step_diff for s in valid_scores]
        report.avg_step_diff = float(np.mean(step_diffs))
        report.std_step_diff = float(np.std(step_diffs, ddof=1)) if len(step_diffs) > 1 else None
        report.avg_target_coverage = sum(s.steps.target_coverage for s in valid_scores) / len(valid_scores)

        # Aggregate semantic scores
        semantic_scores = [s for s in valid_scores if s.semantic.computed]
        if semantic_scores:
            report.semantic_evaluated = len(semantic_scores)
            report.avg_semantic_score = sum(s.semantic.overall_semantic_score for s in semantic_scores) / len(semantic_scores)
            report.avg_summary_similarity = sum(s.semantic.summary_similarity for s in semantic_scores) / len(semantic_scores)
            report.avg_step_similarity = sum(s.semantic.avg_step_similarity for s in semantic_scores) / len(semantic_scores)

    # Convert scores to dict for JSON serialization
    report.pr_scores = [asdict(s) for s in scores]

    return report


def print_batch_report(report: BatchReport):
    """Print the aggregated report."""
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}📊 BATCH EVALUATION REPORT")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")

    print(f"\n{Fore.YELLOW}📈 SUMMARY:{Style.RESET_ALL}")
    print(f"   Total PRs found: {report.total_prs}")
    print(f"   Evaluated: {report.evaluated_prs}")
    print(f"   Skipped (errors): {report.skipped_prs}")

    if report.evaluated_prs == 0:
        print(f"\n{Fore.RED}❌ No PRs evaluated successfully{Style.RESET_ALL}")
        return

    print(f"\n{Fore.YELLOW}📁 FILE IDENTIFICATION (avg):{Style.RESET_ALL}")
    print(f"   Precision: {report.avg_file_precision:.2%}")
    print(f"   Recall: {report.avg_file_recall:.2%}")
    print(f"   F1: {report.avg_file_f1:.2%}")

    print(f"\n{Fore.YELLOW}🔧 FUNCTION IDENTIFICATION (avg):{Style.RESET_ALL}")
    print(f"   Precision: {report.avg_function_precision:.2%}")
    print(f"   Recall: {report.avg_function_recall:.2%}")
    print(f"   F1: {report.avg_function_f1:.2%}")

    print(f"\n{Fore.YELLOW}📋 STEP PLAN (avg):{Style.RESET_ALL}")
    step_diff_str = f"{report.avg_step_diff:+.1f}"
    if report.std_step_diff is not None:
        step_diff_str += f"  (σ = {report.std_step_diff:.2f})"
    print(f"   Step diff: {step_diff_str}")
    print(f"   Target coverage: {report.avg_target_coverage:.2%}")

    # Semantic scores (if computed)
    if report.semantic_evaluated > 0:
        print(f"\n{Fore.YELLOW}🧠 SEMANTIC SIMILARITY (avg):{Style.RESET_ALL}")
        print(f"   PRs evaluated: {report.semantic_evaluated}")
        print(f"   Avg semantic score: {report.avg_semantic_score:.2%}")
        print(f"   Avg summary similarity: {report.avg_summary_similarity:.2%}")
        print(f"   Avg step similarity: {report.avg_step_similarity:.2%}")

    # Overall
    overall_f1 = (report.avg_file_f1 + report.avg_function_f1) / 2
    print(f"\n{Fore.GREEN}📈 OVERALL AVERAGE F1: {overall_f1:.2%}{Style.RESET_ALL}")

    if report.semantic_evaluated > 0:
        combined = (overall_f1 + report.avg_semantic_score) / 2
        print(f"   Combined (F1 + Semantic): {combined:.2%}")

    if overall_f1 >= 0.7:
        print(f"   {Fore.GREEN}✅ High performing system{Style.RESET_ALL}")
    elif overall_f1 >= 0.4:
        print(f"   {Fore.YELLOW}⚠️ Performance can be improved{Style.RESET_ALL}")
    else:
        print(f"   {Fore.RED}❌ Poor performance{Style.RESET_ALL}")


def save_report(report: BatchReport, output_path: str):
    """Save the report in JSON format."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)
        print(f"\n{Fore.GREEN}💾 Report saved: {output_path}{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}❌ Failed to save report to {output_path}: {e}{Style.RESET_ALL}")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate predictions by comparing them with ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate single PR
  python -m GenAI.evaluate_predictions PR4Code/.../pr_123/

  # Evaluate all PRs with predicted_plan.json
  python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py/ --batch

  # Limit to N PRs
  python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py/ --batch --limit 10

  # With semantic analysis (uses OpenAI embeddings, requires API key)
  python -m GenAI.evaluate_predictions PR4Code/.../pr_123/ --semantic
  python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py/ --batch --semantic

  # Save JSON report
  python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py/ --batch --report eval.json

Metrics:
  - Precision: How many predicted files/functions are correct
  - Recall: How many actual files/functions were found
  - F1: Harmonic mean of Precision and Recall
  - Target Coverage: How many step targets match with actual files/functions
  - Semantic Score: Semantic similarity between prediction and ground truth (with --semantic)
        """
    )

    parser.add_argument(
        "path",
        help="Single PR directory or base directory for batch"
    )

    parser.add_argument(
        "--batch",
        action="store_true",
        help="Evaluate all PRs in the directory (recursively)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of PRs to evaluate (only with --batch)"
    )

    parser.add_argument(
        "--report",
        help="Save JSON report to the specified path"
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Minimal output"
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip PRs that already have evaluation_score.json (only with --batch)"
    )

    parser.add_argument(
        "-s", "--semantic",
        action="store_true",
        help="Also compute semantic similarity using OpenAI embeddings (requires OPENAI_API_KEY)"
    )

    args = parser.parse_args()
    path = Path(args.path).resolve()

    if not path.exists():
        print(f"{Fore.RED}❌ Path not found: {path}{Style.RESET_ALL}")
        sys.exit(1)

    # Check API key if semantic is requested
    if args.semantic and not os.getenv('OPENAI_API_KEY'):
        print(f"{Fore.RED}❌ OPENAI_API_KEY not found. Required for --semantic{Style.RESET_ALL}")
        sys.exit(1)

    if args.batch:
        # Batch evaluation
        print(f"{Fore.CYAN}🔍 Searching for PRs with predicted_plan.json and ground_truth.json...{Style.RESET_ALL}")
        report = evaluate_batch(path, args.limit, compute_semantic=args.semantic, skip_existing=args.skip_existing)

        if not args.quiet:
            print_batch_report(report)

        if args.report:
            save_report(report, args.report)

    else:
        # Single PR evaluation
        score = evaluate_single_pr(path, compute_semantic=args.semantic)

        if not args.quiet:
            print_pr_score(score)

        if args.report:
            try:
                with open(args.report, 'w', encoding='utf-8') as f:
                    json.dump(asdict(score), f, indent=2, ensure_ascii=False)
                print(f"\n{Fore.GREEN}💾 Score saved: {args.report}{Style.RESET_ALL}")
            except Exception as e:
                print(f"\n{Fore.RED}❌ Failed to save report to {args.report}: {e}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
