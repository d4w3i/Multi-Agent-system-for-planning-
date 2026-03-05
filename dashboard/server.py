"""
PR4Code Dashboard Server
────────────────────────
Run:
    pip install flask
    python dashboard/server.py

Visit: http://localhost:2002
"""

import json
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_from_directory, session, url_for

_BASE = Path(__file__).parent.parent

DATASETS: dict[str, Path] = {
    "gpt_5-2":             _BASE / "gpt_5-2_evals"   / "first_turn",
    "gpt_5-mini":          _BASE / "gpt_5-mini_evals" / "first_turn",
    "gpt_5-nano":          _BASE / "gpt_5-nano_evals"  / "first_turn",
    "gpt_5-2_ablation":    _BASE / "gpt_5-2_evals"   / "ablation_turn",
    "gpt_5-mini_ablation": _BASE / "gpt_5-mini_evals" / "ablation_turn",
    "gpt_5-nano_ablation": _BASE / "gpt_5-nano_evals"  / "ablation_turn",
}
DEFAULT_EVAL = "gpt_5-2"

STATIC = Path(__file__).parent / "static"

_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "RapidVienn4gain")

app = Flask(__name__, static_folder=str(STATIC))
app.secret_key = os.environ.get("DASHBOARD_SECRET_KEY", "pr4code-dashboard-secret-f7a2")


_LOGIN_HTML = """
<!doctype html>
<html>
<head>
  <title>Dashboard — Login</title>
  <style>
    body { font-family: sans-serif; display: flex; justify-content: center;
           align-items: center; height: 100vh; margin: 0; background: #0f0f0f; color: #eee; }
    form { display: flex; flex-direction: column; gap: 12px; min-width: 280px; }
    h2   { margin: 0 0 8px; }
    input[type=password] { padding: 10px; border: 1px solid #444; border-radius: 6px;
                           background: #1e1e1e; color: #eee; font-size: 15px; }
    button { padding: 10px; background: #4f8ef7; border: none; border-radius: 6px;
             color: #fff; font-size: 15px; cursor: pointer; }
    button:hover { background: #3a7bd5; }
    .err { color: #f77; font-size: 14px; }
  </style>
</head>
<body>
  <form method="post">
    <h2>PR4Code Dashboard</h2>
    {% if error %}<p class="err">Incorrect password.</p>{% endif %}
    <input type="password" name="password" placeholder="Password" autofocus>
    <button type="submit">Enter</button>
  </form>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    error = False
    if request.method == "POST":
        if request.form.get("password") == _PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = True
    return render_template_string(_LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.before_request
def require_auth():
    if request.endpoint in ("login", "static"):
        return
    if not session.get("authenticated"):
        return redirect(url_for("login"))


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

def _quantile(values, q: float):
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    n = len(clean)
    idx = q * (n - 1)
    lo_i, hi_i = int(idx), min(int(idx) + 1, n - 1)
    return round(clean[lo_i] + (idx - lo_i) * (clean[hi_i] - clean[lo_i]), 4)


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


def _histogram_auto(values, n_bins=10):
    """Auto-range histogram; returns {counts, lo, hi} for arbitrary value ranges."""
    clean = [v for v in values if v is not None]
    if not clean:
        return {"counts": [0] * n_bins, "lo": 0, "hi": 1}
    lo = 0
    hi = max(clean)
    counts = _histogram(clean, n_bins, lo=lo, hi=hi if hi > 0 else 1)
    return {"counts": counts, "lo": lo, "hi": float(hi)}


def _histogram_shared(values_list, n_bins=10):
    """Bin multiple series with identical bin edges (shared lo/hi).
    Returns {lo, hi, series: [counts_a, counts_b, ...]} for overlay charts."""
    all_vals = [v for vals in values_list for v in vals if v is not None]
    if not all_vals:
        return {"lo": 0, "hi": 1, "series": [[0] * n_bins for _ in values_list]}
    lo = 0
    hi = max(all_vals)
    effective_hi = hi if hi > 0 else 1
    series = [_histogram(vals, n_bins, lo=lo, hi=effective_hi) for vals in values_list]
    return {"lo": lo, "hi": float(hi), "series": series}


def _histogram_int(values):
    """One bin per integer value; lo = min(values), hi = max(values).
    Handles both positive-only (step counts) and signed (step diffs) data."""
    clean = [int(round(v)) for v in values if v is not None]
    if not clean:
        return {"counts": [], "lo": 0, "hi": 0, "step": 1}
    lo = min(clean)
    hi = max(clean)
    n_bins = hi - lo + 1
    counts = [0] * n_bins
    for v in clean:
        counts[v - lo] += 1
    return {"counts": counts, "lo": float(lo), "hi": float(hi), "step": 1}


def _has_empty_fn(plan_json) -> bool:
    """Return True if any step in step_plan.steps has an empty function_to_modify."""
    if not plan_json:
        return False
    steps = (plan_json.get("step_plan") or {}).get("steps") or []
    return any(not (s.get("function_to_modify") or "").strip() for s in steps)


def _pr_summary(repo_dir_name: str, pr_dir: Path) -> dict | None:
    data = _load(pr_dir / "data.json")
    if not data:
        return None

    score = _load(pr_dir / "evaluation_score.json")
    tokens = _load(pr_dir / "token_usage.json")
    session = _load(pr_dir / "session_log.json")

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

    gt_data   = _load(pr_dir / "ground_truth.json")
    pred_data = _load(pr_dir / "predicted_plan.json")
    result["has_empty_function_step"] = _has_empty_fn(gt_data) or _has_empty_fn(pred_data)
    result["empty_fn_in_gt"]          = _has_empty_fn(gt_data)
    result["empty_fn_in_pred"]        = _has_empty_fn(pred_data)

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
        result["total_tokens"]        = tokens.get("total_tokens", 0)
        result["total_input_tokens"]  = tokens.get("total_input_tokens", 0)
        result["total_output_tokens"] = tokens.get("total_output_tokens", 0)
        result["total_requests"]      = tokens.get("total_requests", 0)
        result["model"]               = tokens.get("model_name", "")
        dur = tokens.get("duration_seconds")
        if dur is None and session:
            dur = session.get("duration_seconds")
        result["duration_seconds"]    = dur
        agents_list = tokens.get("agents", [])
        agent_map   = {a["agent_name"]: a.get("total_tokens", 0)
                       for a in agents_list if "agent_name" in a}
        result["agent1_tokens"] = agent_map.get("analysis_agent")
        result["agent2_tokens"] = agent_map.get("context_planner_agent")
    else:
        result["total_tokens"]        = None
        result["total_input_tokens"]  = None
        result["total_output_tokens"] = None
        result["total_requests"]      = None
        result["model"]               = ""
        result["duration_seconds"]    = session.get("duration_seconds") if session else None
        result["agent1_tokens"]       = None
        result["agent2_tokens"]       = None

    # ── tool call info ───────────────────────────────────────────────────────
    if session:
        tc_total: int = 0
        tc_by_agent: dict[str, int] = {}
        tc_by_tool:  dict[str, int] = {}
        for agent in session.get("agents", []):
            agent_name = agent.get("name", "unknown")
            calls = agent.get("tool_calls", [])
            count = len(calls)
            tc_total += count
            tc_by_agent[agent_name] = tc_by_agent.get(agent_name, 0) + count
            for call in calls:
                tool_name = call.get("tool_name", "unknown")
                tc_by_tool[tool_name] = tc_by_tool.get(tool_name, 0) + 1
        result["tool_calls_total"]    = tc_total
        result["tool_calls_by_agent"] = tc_by_agent
        result["tool_calls_by_tool"]  = tc_by_tool
    else:
        result["tool_calls_total"]    = None
        result["tool_calls_by_agent"] = {}
        result["tool_calls_by_tool"]  = {}

    return result


_cache: dict = {k: {"prs": None, "ts": 0.0} for k in DATASETS}
_CACHE_TTL = 60  # seconds


def _collect_prs(eval_key: str = DEFAULT_EVAL) -> list[dict]:
    if eval_key not in DATASETS:
        eval_key = DEFAULT_EVAL
    c = _cache[eval_key]
    now = time.monotonic()
    if c["prs"] is not None and now - c["ts"] < _CACHE_TTL:
        return c["prs"]

    prs = []
    dataset = DATASETS[eval_key]
    if not dataset.exists():
        return prs
    for repo_dir in sorted(dataset.iterdir()):
        if not repo_dir.is_dir():
            continue
        for pr_dir in sorted(repo_dir.iterdir()):
            if not pr_dir.is_dir() or not pr_dir.name.startswith("pr_"):
                continue
            pr = _pr_summary(repo_dir.name, pr_dir)
            if pr:
                prs.append(pr)

    c["prs"] = prs
    c["ts"] = now
    return prs


# ─── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/datasets")
def api_datasets():
    return jsonify({
        k: {"exists": v.exists(), "label": k.replace("_", "-")}
        for k, v in DATASETS.items()
    })


@app.route("/api/summary")
def api_summary():
    eval_key  = request.args.get("eval", DEFAULT_EVAL)
    prs       = _collect_prs(eval_key)
    evaluated = [p for p in prs if p["has_score"] and not p["has_eval_error"]]
    repos     = sorted({p["repository"] for p in prs if p.get("repository")})

    eval_with_empty = [p for p in evaluated if p.get("empty_fn_in_gt")]
    eval_without    = [p for p in evaluated if not p.get("empty_fn_in_gt")]

    # subset: evaluated PRs where ground truth has NO empty function_to_modify fields
    clean_gt = [p for p in evaluated if not p.get("empty_fn_in_gt")]
    cgt_f1_vals   = [p["files_f1"]     for p in clean_gt if p["files_f1"]     is not None]
    cgt_func_vals = [p["functions_f1"] for p in clean_gt if p["functions_f1"] is not None]
    cgt_sem_vals  = [p["semantic"]     for p in clean_gt if p["semantic"]      is not None]
    cgt_dur_vals  = [p["duration_seconds"] for p in clean_gt if p.get("duration_seconds") is not None]

    cgt_steps_with_data = [
        p for p in clean_gt
        if p.get("steps_predicted") is not None and p.get("steps_actual") is not None
    ]
    cgt_steps_actual_vals = [p["steps_actual"]    for p in cgt_steps_with_data]
    cgt_steps_pred_vals   = [p["steps_predicted"]  for p in cgt_steps_with_data]
    cgt_step_diffs        = [p["steps_predicted"] - p["steps_actual"] for p in cgt_steps_with_data]
    cgt_abs_diff_vals     = [abs(d) for d in cgt_step_diffs]
    cgt_total_token_vals  = [p["total_tokens"]   for p in clean_gt if p.get("total_tokens")   is not None]
    cgt_agent1_vals       = [p["agent1_tokens"]  for p in clean_gt if p.get("agent1_tokens")  is not None]
    cgt_agent2_vals       = [p["agent2_tokens"]  for p in clean_gt if p.get("agent2_tokens")  is not None]
    cgt_req_vals          = [p["total_requests"] for p in clean_gt if p.get("total_requests") is not None]
    cgt_prs_with_tc       = [p for p in clean_gt if p.get("tool_calls_total") is not None]
    cgt_agent_names: set[str] = set()
    cgt_tool_names:  set[str] = set()
    for p in cgt_prs_with_tc:
        cgt_agent_names.update(p.get("tool_calls_by_agent", {}).keys())
        cgt_tool_names.update(p.get("tool_calls_by_tool",  {}).keys())
    cgt_avg_tc_by_agent = {
        name: _avg(p["tool_calls_by_agent"].get(name, 0) for p in cgt_prs_with_tc)
        for name in sorted(cgt_agent_names)
    }
    cgt_avg_tc_by_tool = {
        name: _avg(p["tool_calls_by_tool"].get(name, 0) for p in cgt_prs_with_tc)
        for name in sorted(cgt_tool_names)
    }

    clean_gt_stats = {
        "n":                     len(clean_gt),
        # files F1
        "avg_files_f1":          _avg(cgt_f1_vals),
        "min_files_f1":          round(min(cgt_f1_vals), 4)  if cgt_f1_vals  else None,
        "q1_files_f1":           _quantile(cgt_f1_vals, 0.25),
        "median_files_f1":       _median(cgt_f1_vals),
        "q3_files_f1":           _quantile(cgt_f1_vals, 0.75),
        "max_files_f1":          round(max(cgt_f1_vals), 4)  if cgt_f1_vals  else None,
        # functions F1
        "avg_functions_f1":      _avg(cgt_func_vals),
        "min_functions_f1":      round(min(cgt_func_vals), 4) if cgt_func_vals else None,
        "q1_functions_f1":       _quantile(cgt_func_vals, 0.25),
        "median_functions_f1":   _median(cgt_func_vals),
        "q3_functions_f1":       _quantile(cgt_func_vals, 0.75),
        "max_functions_f1":      round(max(cgt_func_vals), 4) if cgt_func_vals else None,
        # semantic
        "avg_semantic":          _avg(cgt_sem_vals),
        "min_semantic":          round(min(cgt_sem_vals), 4)  if cgt_sem_vals  else None,
        "q1_semantic":           _quantile(cgt_sem_vals, 0.25),
        "median_semantic":       _median(cgt_sem_vals),
        "q3_semantic":           _quantile(cgt_sem_vals, 0.75),
        "max_semantic":          round(max(cgt_sem_vals), 4)  if cgt_sem_vals  else None,
        # duration
        "avg_duration_seconds":  _avg(cgt_dur_vals),
        "stdev_duration_seconds":_stdev(cgt_dur_vals),
        "min_duration_seconds":  min(cgt_dur_vals)            if cgt_dur_vals  else None,
        "q1_duration_seconds":   _quantile(cgt_dur_vals, 0.25),
        "median_duration_seconds": _median(cgt_dur_vals),
        "q3_duration_seconds":   _quantile(cgt_dur_vals, 0.75),
        "max_duration_seconds":  max(cgt_dur_vals)            if cgt_dur_vals  else None,
        # steps actual
        "avg_steps_actual":      _avg(cgt_steps_actual_vals),
        "stdev_steps_actual":    _stdev(cgt_steps_actual_vals),
        "q1_steps_actual":       _quantile(cgt_steps_actual_vals, 0.25),
        "median_steps_actual":   _median(cgt_steps_actual_vals),
        "q3_steps_actual":       _quantile(cgt_steps_actual_vals, 0.75),
        "min_steps_actual":      min(cgt_steps_actual_vals) if cgt_steps_actual_vals else None,
        "max_steps_actual":      max(cgt_steps_actual_vals) if cgt_steps_actual_vals else None,
        # steps predicted
        "avg_steps_predicted":   _avg(cgt_steps_pred_vals),
        "stdev_steps_predicted": _stdev(cgt_steps_pred_vals),
        "q1_steps_predicted":    _quantile(cgt_steps_pred_vals, 0.25),
        "median_steps_predicted":_median(cgt_steps_pred_vals),
        "q3_steps_predicted":    _quantile(cgt_steps_pred_vals, 0.75),
        "min_steps_predicted":   min(cgt_steps_pred_vals) if cgt_steps_pred_vals else None,
        "max_steps_predicted":   max(cgt_steps_pred_vals) if cgt_steps_pred_vals else None,
        # abs step diff
        "avg_abs_step_diff":     _avg(cgt_abs_diff_vals),
        "stdev_abs_step_diff":   _stdev(cgt_abs_diff_vals),
        "q1_abs_step_diff":      _quantile(cgt_abs_diff_vals, 0.25),
        "median_abs_step_diff":  _median(cgt_abs_diff_vals),
        "q3_abs_step_diff":      _quantile(cgt_abs_diff_vals, 0.75),
        "min_abs_step_diff":     min(cgt_abs_diff_vals) if cgt_abs_diff_vals else None,
        "max_abs_step_diff":     max(cgt_abs_diff_vals) if cgt_abs_diff_vals else None,
        # total tokens
        "avg_total_tokens":      _avg(cgt_total_token_vals),
        "stdev_total_tokens":    _stdev(cgt_total_token_vals),
        "q1_total_tokens":       _quantile(cgt_total_token_vals, 0.25),
        "median_total_tokens":   _median(cgt_total_token_vals),
        "q3_total_tokens":       _quantile(cgt_total_token_vals, 0.75),
        "min_total_tokens":      min(cgt_total_token_vals) if cgt_total_token_vals else None,
        "max_total_tokens":      max(cgt_total_token_vals) if cgt_total_token_vals else None,
        # agent 1 tokens
        "avg_agent1_tokens":     _avg(cgt_agent1_vals),
        "stdev_agent1_tokens":   _stdev(cgt_agent1_vals),
        "q1_agent1_tokens":      _quantile(cgt_agent1_vals, 0.25),
        "median_agent1_tokens":  _median(cgt_agent1_vals),
        "q3_agent1_tokens":      _quantile(cgt_agent1_vals, 0.75),
        "min_agent1_tokens":     min(cgt_agent1_vals) if cgt_agent1_vals else None,
        "max_agent1_tokens":     max(cgt_agent1_vals) if cgt_agent1_vals else None,
        # agent 2 tokens
        "avg_agent2_tokens":     _avg(cgt_agent2_vals),
        "stdev_agent2_tokens":   _stdev(cgt_agent2_vals),
        "q1_agent2_tokens":      _quantile(cgt_agent2_vals, 0.25),
        "median_agent2_tokens":  _median(cgt_agent2_vals),
        "q3_agent2_tokens":      _quantile(cgt_agent2_vals, 0.75),
        "min_agent2_tokens":     min(cgt_agent2_vals) if cgt_agent2_vals else None,
        "max_agent2_tokens":     max(cgt_agent2_vals) if cgt_agent2_vals else None,
        # API requests
        "avg_total_requests":    _avg(cgt_req_vals),
        "stdev_total_requests":  _stdev(cgt_req_vals),
        "q1_total_requests":     _quantile(cgt_req_vals, 0.25),
        "median_total_requests": _median(cgt_req_vals),
        "q3_total_requests":     _quantile(cgt_req_vals, 0.75),
        "min_total_requests":    min(cgt_req_vals) if cgt_req_vals else None,
        "max_total_requests":    max(cgt_req_vals) if cgt_req_vals else None,
        # tool calls
        "avg_tool_calls":          _avg(p["tool_calls_total"] for p in cgt_prs_with_tc),
        "avg_tool_calls_by_agent": cgt_avg_tc_by_agent,
        "avg_tool_calls_by_tool":  cgt_avg_tc_by_tool,
    }

    chart_data = [
        {
            "id":       p["id"],
            "title":    p["title"][:80],
            "repo":     p["repository"],
            "tokens":   p["total_tokens"],
            "tool_calls": p.get("tool_calls_total"),
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
            "duration":          p.get("duration_seconds"),
            "empty_fn_in_gt":    p.get("empty_fn_in_gt", False),
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
    avg_step_diff = round(statistics.mean(abs(d) for d in step_diffs), 3) if step_diffs else None
    std_step_diff = round(statistics.stdev(step_diffs), 3) if len(step_diffs) > 1 else None

    steps_actual_vals = [p["steps_actual"]    for p in steps_with_data]
    steps_pred_vals   = [p["steps_predicted"]  for p in steps_with_data]
    abs_diff_vals     = [abs(d) for d in step_diffs]

    total_token_vals = [p["total_tokens"]       for p in prs if p.get("total_tokens")       is not None]
    agent1_vals      = [p["agent1_tokens"]      for p in prs if p.get("agent1_tokens")      is not None]
    agent2_vals      = [p["agent2_tokens"]      for p in prs if p.get("agent2_tokens")      is not None]
    dur_vals         = [p["duration_seconds"]   for p in prs if p.get("duration_seconds")   is not None]
    req_vals         = [p["total_requests"]     for p in prs if p.get("total_requests")     is not None]

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

    # ── tool call aggregation ────────────────────────────────────────────────
    prs_with_tc = [p for p in prs if p.get("tool_calls_total") is not None]
    agent_names_set: set[str] = set()
    tool_names_set:  set[str] = set()
    for p in prs_with_tc:
        agent_names_set.update(p.get("tool_calls_by_agent", {}).keys())
        tool_names_set.update(p.get("tool_calls_by_tool",  {}).keys())
    avg_tc_by_agent = {
        name: _avg(p["tool_calls_by_agent"].get(name, 0) for p in prs_with_tc)
        for name in sorted(agent_names_set)
    }
    avg_tc_by_tool = {
        name: _avg(p["tool_calls_by_tool"].get(name, 0) for p in prs_with_tc)
        for name in sorted(tool_names_set)
    }

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
        # steps distribution
        "stdev_steps_actual":      _stdev(steps_actual_vals),
        "q1_steps_actual":         _quantile(steps_actual_vals, 0.25),
        "median_steps_actual":     _median(steps_actual_vals),
        "q3_steps_actual":         _quantile(steps_actual_vals, 0.75),
        "min_steps_actual":        min(steps_actual_vals)   if steps_actual_vals else None,
        "max_steps_actual":        max(steps_actual_vals)   if steps_actual_vals else None,
        "stdev_steps_predicted":   _stdev(steps_pred_vals),
        "q1_steps_predicted":      _quantile(steps_pred_vals, 0.25),
        "median_steps_predicted":  _median(steps_pred_vals),
        "q3_steps_predicted":      _quantile(steps_pred_vals, 0.75),
        "min_steps_predicted":     min(steps_pred_vals)     if steps_pred_vals else None,
        "max_steps_predicted":     max(steps_pred_vals)     if steps_pred_vals else None,
        "avg_abs_step_diff":       avg_step_diff,
        "stdev_abs_step_diff":     _stdev(abs_diff_vals),
        "q1_abs_step_diff":        _quantile(abs_diff_vals, 0.25),
        "median_abs_step_diff":    _median(abs_diff_vals),
        "q3_abs_step_diff":        _quantile(abs_diff_vals, 0.75),
        "min_abs_step_diff":       min(abs_diff_vals)       if abs_diff_vals else None,
        "max_abs_step_diff":       max(abs_diff_vals)       if abs_diff_vals else None,
        # tokens
        "avg_total_tokens":   _avg(
            p["total_tokens"] for p in prs if p.get("total_tokens") is not None
        ),
        "avg_input_tokens":   _avg(
            p["total_input_tokens"] for p in prs if p.get("total_input_tokens") is not None
        ),
        "avg_output_tokens":  _avg(
            p["total_output_tokens"] for p in prs if p.get("total_output_tokens") is not None
        ),
        "avg_total_requests":    _avg(
            p["total_requests"] for p in prs if p.get("total_requests") is not None
        ),
        "stdev_total_requests":  _stdev(req_vals),
        "q1_total_requests":     _quantile(req_vals, 0.25),
        "median_total_requests": _median(req_vals),
        "q3_total_requests":     _quantile(req_vals, 0.75),
        "min_total_requests":    min(req_vals) if req_vals else None,
        "max_total_requests":    max(req_vals) if req_vals else None,
        "avg_duration_seconds":    _avg(dur_vals),
        "stdev_duration_seconds":  _stdev(dur_vals),
        "q1_duration_seconds":     _quantile(dur_vals, 0.25),
        "median_duration_seconds": _median(dur_vals),
        "q3_duration_seconds":     _quantile(dur_vals, 0.75),
        "min_duration_seconds":    min(dur_vals) if dur_vals else None,
        "max_duration_seconds":    max(dur_vals) if dur_vals else None,
        # per-agent token distribution
        "avg_agent1_tokens":    _avg(agent1_vals),
        "stdev_agent1_tokens":  _stdev(agent1_vals),
        "q1_agent1_tokens":     _quantile(agent1_vals, 0.25),
        "median_agent1_tokens": _median(agent1_vals),
        "q3_agent1_tokens":     _quantile(agent1_vals, 0.75),
        "min_agent1_tokens":    min(agent1_vals) if agent1_vals else None,
        "max_agent1_tokens":    max(agent1_vals) if agent1_vals else None,
        "avg_agent2_tokens":    _avg(agent2_vals),
        "stdev_agent2_tokens":  _stdev(agent2_vals),
        "q1_agent2_tokens":     _quantile(agent2_vals, 0.25),
        "median_agent2_tokens": _median(agent2_vals),
        "q3_agent2_tokens":     _quantile(agent2_vals, 0.75),
        "min_agent2_tokens":    min(agent2_vals) if agent2_vals else None,
        "max_agent2_tokens":    max(agent2_vals) if agent2_vals else None,
        "stdev_total_tokens":   _stdev(total_token_vals),
        "q1_total_tokens":      _quantile(total_token_vals, 0.25),
        "median_total_tokens":  _median(total_token_vals),
        "q3_total_tokens":      _quantile(total_token_vals, 0.75),
        "min_total_tokens":     min(total_token_vals) if total_token_vals else None,
        "max_total_tokens":     max(total_token_vals) if total_token_vals else None,
        # files F1 distribution stats
        "q1_files_f1":            _quantile(f1_vals, 0.25),
        "q3_files_f1":            _quantile(f1_vals, 0.75),
        "min_files_f1":           round(min(f1_vals), 4) if f1_vals else None,
        "max_files_f1":           round(max(f1_vals), 4) if f1_vals else None,
        # functions F1 additional stats
        "median_functions_f1":    _median(func_f1_vals),
        "stdev_functions_f1":     _stdev(func_f1_vals),
        "q1_functions_f1":        _quantile(func_f1_vals, 0.25),
        "q3_functions_f1":        _quantile(func_f1_vals, 0.75),
        "min_functions_f1":       round(min(func_f1_vals), 4) if func_f1_vals else None,
        "max_functions_f1":       round(max(func_f1_vals), 4) if func_f1_vals else None,
        # semantic additional stats
        "stdev_semantic":         _stdev(sem_vals),
        "q1_semantic":            _quantile(sem_vals, 0.25),
        "q3_semantic":            _quantile(sem_vals, 0.75),
        "min_semantic":           round(min(sem_vals), 4) if sem_vals else None,
        "max_semantic":           round(max(sem_vals), 4) if sem_vals else None,
        # distributions (0-1 metrics)
        "f1_distribution":          _histogram(f1_vals),
        "functions_f1_distribution":_histogram(func_f1_vals),
        "semantic_distribution":    _histogram(sem_vals),
        # distributions (auto-range for steps / tokens)
        "steps_actual_distribution":    _histogram_int(steps_actual_vals),
        "steps_predicted_distribution": _histogram_int(steps_pred_vals),
        "abs_diff_distribution":        _histogram_auto(abs_diff_vals),
        "step_diff_distribution":       _histogram_int(step_diffs),
        "agent1_tokens_distribution":   _histogram_auto(agent1_vals),
        "agent2_tokens_distribution":   _histogram_auto(agent2_vals),
        "total_tokens_distribution":    _histogram_auto(total_token_vals),
        "agents_overlay_distribution":  _histogram_shared([agent1_vals, agent2_vals]),
        "duration_distribution":        _histogram_auto(dur_vals),
        "requests_distribution":        _histogram_int(req_vals),
        # per-repo
        "per_repo":          per_repo,
        "repositories":      repos,
        "chart_data":        chart_data,
        "steps_chart_data":  steps_chart_data,
        # tool calls
        "avg_tool_calls":          _avg(p["tool_calls_total"] for p in prs_with_tc),
        "avg_tool_calls_by_agent": avg_tc_by_agent,
        "avg_tool_calls_by_tool":  avg_tc_by_tool,
        "prs_with_tool_data":      len(prs_with_tc),
        # empty-function step subset comparison
        "count_with_empty_fn":    len(eval_with_empty),
        "count_without_empty_fn": len(eval_without),
        "empty_fn_comparison": {
            "with": {
                "avg_files_f1":     _avg(p["files_f1"]     for p in eval_with_empty),
                "avg_functions_f1": _avg(p["functions_f1"] for p in eval_with_empty),
                "avg_semantic":     _avg(p["semantic"]      for p in eval_with_empty),
            },
            "without": {
                "avg_files_f1":     _avg(p["files_f1"]     for p in eval_without),
                "avg_functions_f1": _avg(p["functions_f1"] for p in eval_without),
                "avg_semantic":     _avg(p["semantic"]      for p in eval_without),
            },
        },
        # clean GT subset (no empty function_to_modify in ground truth)
        "clean_gt_stats":    clean_gt_stats,
        # eval metadata
        "eval_key":          eval_key,
    })


@app.route("/api/prs")
def api_prs():
    eval_key = request.args.get("eval", DEFAULT_EVAL)
    return jsonify(_collect_prs(eval_key))


@app.route("/api/pr/<path:pr_id>")
def api_pr_detail(pr_id: str):
    eval_key = request.args.get("eval", DEFAULT_EVAL)
    dataset  = DATASETS.get(eval_key, DATASETS[DEFAULT_EVAL])
    parts = pr_id.split("/", 1)
    if len(parts) != 2:
        abort(404)
    repo_dir_name, pr_name = parts
    pr_dir = dataset / repo_dir_name / pr_name
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
    for key, path in DATASETS.items():
        status = "✓" if path.exists() else "✗ (missing)"
        print(f"  ◆ [{key}] {path}  {status}")
    print(f"  ◆ URL     : http://localhost:2002")
    print()
    app.run(debug=False, port=2002)
