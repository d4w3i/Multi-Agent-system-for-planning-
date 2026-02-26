#!/usr/bin/env python3
"""
PR4Code Dashboard Server
────────────────────────
Run:
    pip install flask
    python dashboard/server.py

Visit: http://localhost:5000
"""

import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

DATASET = Path(__file__).parent.parent / "PR4Code" / "dataset_pr_commits_py"
STATIC = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC))


# ─── helpers ──────────────────────────────────────────────────────────────────

def _load(path: Path):
    """Safely load a JSON file; return None on any failure."""
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _avg(values):
    clean = [v for v in values if v is not None]
    return round(statistics.mean(clean), 4) if clean else 0

def _median(values):
    clean = [v for v in values if v is not None]
    return round(statistics.median(clean), 4) if clean else None

def _stdev(values):
    clean = [v for v in values if v is not None]
    return round(statistics.stdev(clean), 4) if len(clean) > 1 else None

def _histogram(values, n_bins=10, lo=0.0, hi=1.0):
    counts = [0] * n_bins
    width = (hi - lo) / n_bins
    for v in values:
        if v is None:
            continue
        idx = min(int((v - lo) / width), n_bins - 1)
        if 0 <= idx < n_bins:
            counts[idx] += 1
    return counts


def _pr_summary(repo_dir_name: str, pr_dir: Path) -> dict | None:
    data = _load(pr_dir / "data.json")
    if not data:
        return None

    score = _load(pr_dir / "evaluation_score.json")
    tokens = _load(pr_dir / "token_usage.json")

    has_score = score is not None
    has_eval_error = bool(score.get("error")) if has_score else False

    result: dict = {
        "id": f"{repo_dir_name}/{pr_dir.name}",
        "repo_dir": repo_dir_name,
        "pr_name": pr_dir.name,
        "pr_num": data.get("pull_request_number"),
        "title": data.get("title", ""),
        "repository": data.get("repository", ""),
        "pr_date": data.get("pr_date", ""),
        "pr_url": data.get("pull_request_url", ""),
        "has_score": has_score,
        "has_eval_error": has_eval_error,
        "has_prediction": (pr_dir / "predicted_plan.json").exists(),
        "has_ground_truth": (pr_dir / "ground_truth.json").exists(),
        "has_session_log": (pr_dir / "session_log.json").exists(),
    }

    # ── evaluation metrics ──────────────────────────────────────────────────
    if has_score and not has_eval_error:
        files = score.get("files", {})
        funcs = score.get("functions", {})
        steps = score.get("steps", {})
        sem   = score.get("semantic", {})
        result.update({
            "files_f1":          files.get("f1", 0),
            "files_precision":   files.get("precision", 0),
            "files_recall":      files.get("recall", 0),
            "functions_f1":      funcs.get("f1", 0),
            "functions_precision": funcs.get("precision", 0),
            "functions_recall":  funcs.get("recall", 0),
            "steps_predicted":   steps.get("predicted_steps"),
            "steps_actual":      steps.get("actual_steps"),
            "target_coverage":   steps.get("target_coverage"),
            "semantic":          sem.get("overall_semantic_score", 0),
            "summary_similarity": sem.get("summary_similarity", 0),
            "evaluated_at":      score.get("evaluated_at", ""),
        })
    else:
        result.update({
            k: None for k in [
                "files_f1", "files_precision", "files_recall",
                "functions_f1", "functions_precision", "functions_recall",
                "steps_predicted", "steps_actual", "target_coverage",
                "semantic", "summary_similarity", "evaluated_at",
            ]
        })

    # ── token info ──────────────────────────────────────────────────────────
    if tokens:
        result["total_tokens"]   = tokens.get("total_tokens", 0)
        result["total_requests"] = tokens.get("total_requests", 0)
        result["model"]          = tokens.get("model_name", "")
    else:
        result["total_tokens"]   = None
        result["total_requests"] = None
        result["model"]          = ""

    return result


_cache: dict = {"prs": None, "ts": 0.0}
_CACHE_TTL = 60  # seconds


def _collect_prs() -> list[dict]:
    now = time.monotonic()
    if _cache["prs"] is not None and now - _cache["ts"] < _CACHE_TTL:
        return _cache["prs"]

    prs = []
    if not DATASET.exists():
        return prs
    for repo_dir in sorted(DATASET.iterdir()):
        if not repo_dir.is_dir():
            continue
        for pr_dir in sorted(repo_dir.iterdir()):
            if not pr_dir.is_dir() or not pr_dir.name.startswith("pr_"):
                continue
            pr = _pr_summary(repo_dir.name, pr_dir)
            if pr:
                prs.append(pr)

    _cache["prs"] = prs
    _cache["ts"] = now
    return prs


# ─── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/summary")
def api_summary():
    prs       = _collect_prs()
    evaluated = [p for p in prs if p["has_score"] and not p["has_eval_error"]]
    repos     = sorted({p["repository"] for p in prs if p.get("repository")})

    chart_data = [
        {
            "id":       p["id"],
            "title":    p["title"][:80],
            "repo":     p["repository"],
            "tokens":   p["total_tokens"],
            "requests": p.get("total_requests") or 0,
            "files_f1":          p["files_f1"],
            "files_precision":   p["files_precision"],
            "files_recall":      p["files_recall"],
            "functions_f1":      p["functions_f1"],
            "semantic":          p.get("semantic") or 0,
            "summary_similarity":p.get("summary_similarity") or 0,
            "steps_predicted":   p.get("steps_predicted"),
            "steps_actual":      p.get("steps_actual"),
            "target_coverage":   p.get("target_coverage") or 0,
        }
        for p in evaluated
        if p.get("total_tokens") is not None
    ]

    f1_vals       = [p["files_f1"]     for p in evaluated if p["files_f1"]     is not None]
    func_f1_vals  = [p["functions_f1"] for p in evaluated if p["functions_f1"] is not None]
    sem_vals      = [p["semantic"]     for p in evaluated if p["semantic"]      is not None]

    repo_map: dict = defaultdict(list)
    for p in prs:
        if p.get("repository"):
            repo_map[p["repository"]].append(p)
    per_repo = []
    for repo, rps in sorted(repo_map.items()):
        rev = [p for p in rps if p["has_score"] and not p["has_eval_error"]]
        per_repo.append({
            "repo":                repo,
            "total":               len(rps),
            "evaluated":           len(rev),
            "with_prediction":     sum(1 for p in rps if p["has_prediction"]),
            "with_ground_truth":   sum(1 for p in rps if p["has_ground_truth"]),
            "avg_files_f1":        _avg(p["files_f1"]     for p in rev),
            "avg_functions_f1":    _avg(p["functions_f1"] for p in rev),
            "avg_semantic":        _avg(p["semantic"]      for p in rev),
        })

    steps_with_data = [
        p for p in evaluated
        if p.get("steps_predicted") is not None and p.get("steps_actual") is not None
    ]
    step_diffs = [p["steps_predicted"] - p["steps_actual"] for p in steps_with_data]
    avg_step_diff = round(statistics.mean(step_diffs), 3) if step_diffs else None
    std_step_diff = round(statistics.stdev(step_diffs), 3) if len(step_diffs) > 1 else None

    # separate chart data for steps — includes ALL evaluated PRs with step data,
    # not just those that also have token_usage.json
    steps_chart_data = [
        {
            "id":              p["id"],
            "title":           p["title"][:80],
            "repo":            p["repository"],
            "steps_predicted": p["steps_predicted"],
            "steps_actual":    p["steps_actual"],
        }
        for p in steps_with_data
    ]

    return jsonify({
        "total_prs":          len(prs),
        "evaluated_prs":      len(evaluated),
        "with_prediction":    sum(1 for p in prs if p["has_prediction"]),
        "with_ground_truth":  sum(1 for p in prs if p["has_ground_truth"]),
        # files
        "avg_files_f1":          _avg(p["files_f1"]         for p in evaluated),
        "avg_files_precision":   _avg(p["files_precision"]   for p in evaluated),
        "avg_files_recall":      _avg(p["files_recall"]      for p in evaluated),
        "median_files_f1":       _median(f1_vals),
        "stdev_files_f1":        _stdev(f1_vals),
        # functions
        "avg_functions_f1":          _avg(p["functions_f1"]          for p in evaluated),
        "avg_functions_precision":   _avg(p["functions_precision"]    for p in evaluated),
        "avg_functions_recall":      _avg(p["functions_recall"]       for p in evaluated),
        # semantic
        "avg_semantic":          _avg(p["semantic"]           for p in evaluated),
        "median_semantic":       _median(sem_vals),
        "avg_summary_similarity":_avg(p["summary_similarity"] for p in evaluated
                                      if p.get("summary_similarity") is not None),
        # steps
        "avg_steps_actual":    _avg(p["steps_actual"]    for p in evaluated
                                    if p.get("steps_actual") is not None),
        "avg_steps_predicted": _avg(p["steps_predicted"] for p in evaluated
                                    if p.get("steps_predicted") is not None),
        "avg_target_coverage": _avg(p["target_coverage"] for p in evaluated
                                    if p.get("target_coverage") is not None),
        "avg_step_diff":  avg_step_diff,
        "std_step_diff":  std_step_diff,
        # tokens
        "avg_total_tokens":   _avg(
            p["total_tokens"] for p in prs if p.get("total_tokens") is not None
        ),
        "avg_total_requests": _avg(
            p["total_requests"] for p in prs if p.get("total_requests") is not None
        ),
        # distributions
        "f1_distribution":          _histogram(f1_vals),
        "functions_f1_distribution":_histogram(func_f1_vals),
        "semantic_distribution":    _histogram(sem_vals),
        # per-repo
        "per_repo":          per_repo,
        "repositories":      repos,
        "chart_data":        chart_data,
        "steps_chart_data":  steps_chart_data,
    })


@app.route("/api/prs")
def api_prs():
    return jsonify(_collect_prs())


@app.route("/api/pr/<path:pr_id>")
def api_pr_detail(pr_id: str):
    parts = pr_id.split("/", 1)
    if len(parts) != 2:
        abort(404)
    repo_dir_name, pr_name = parts
    pr_dir = DATASET / repo_dir_name / pr_name
    if not pr_dir.exists():
        abort(404)

    return jsonify({
        "data":        _load(pr_dir / "data.json"),
        "score":       _load(pr_dir / "evaluation_score.json"),
        "tokens":      _load(pr_dir / "token_usage.json"),
        "ground_truth":_load(pr_dir / "ground_truth.json"),
        "prediction":  _load(pr_dir / "predicted_plan.json"),
        "session_log": _load(pr_dir / "session_log.json"),
    })


if __name__ == "__main__":
    print()
    print("  ◆ PR4Code Evaluation Dashboard")
    print(f"  ◆ Dataset : {DATASET}")
    print(f"  ◆ URL     : http://localhost:2002")
    print()
    app.run(debug=False, port=2002)
