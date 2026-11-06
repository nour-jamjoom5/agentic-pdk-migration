"""Connects Nour's evaluator (repo-root `evaluator/`) to the CHIA loop.

The loop calls  evaluate(obj_dir, run_result) -> dict  (same interface as
eval_stub.py). This adapter:
  1. runs Nour's evaluate_stage() on each Hammer stage the loop ran (syn, par),
     using the tool log (genus.log / innovus.log) when it exists, else the
     Hammer driver log (which holds Python-side errors like a bad PDK path);
  2. turns her per-stage pass/fail into the README's rung ladder;
  3. drops error codes we know are harmless (from the open-PDK baseline run),
     and pulls the first real error lines out of the logs so the agent sees an
     actual message, not just a code count.

Nour's files are used as-is; nothing in evaluator/ is modified.

Run standalone to re-score an existing build dir (no Ray needed):
    python evaluator_adapter.py /scratch/cs199-aau/pdk-migration/runs/seed/build
"""
import glob
import json
import os
import re
import sys
from pathlib import Path

# evaluator/ lives at the repo root, one level above loop/.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evaluator.condense_log import condense_log      # noqa: E402  (Nour)
from evaluator.evaluate import evaluate_stage        # noqa: E402  (Nour)

# Error codes that showed up in a *clean* open-SKY130 GCD run (baseline/NOTES.md).
# They are reported to the agent separately, never treated as the failure cause.
BENIGN_ERROR_CODES = {
    "TECHLIB-702",   # open PDK .lib: related_bias_pin VNB on lsbuf (level-shifter) cells
    "IMPLF-24",      # open PDK IO LEF: VSSIO pin defined twice
    "IMPDB-1221",    # Hammer's generic vdd/vss global-connect patterns match nothing
    "IMPMSMV-3502",  # VPWR/VPB/vdd not in a CPF power domain (single-supply design)
    "IMPSP-2002",    # "density 100%" in late refinePlace, after fillers
    "IMPSP-9022",    # refinePlace completed with errors (same event)
}

TOOL_LOGS = {"syn": "genus.log", "par": "innovus.log"}

_ERR_LINE = re.compile(
    r"\*\*ERROR|^\s*Error\b|^ERROR\b|^\w+(Error|Exception)\b:|Cannot obtain .* license",
    re.IGNORECASE)
_CODE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
# Innovus/Genus end-of-log message summary table, e.g.
#   "ERROR     IMPSP-2002           1  Density too high (%.1f%%), ..."
# It recaps counts of messages already reported above -- not an error occurrence.
_SUMMARY_ROW = re.compile(r"^\s*(ERROR|WARNING|WARN|INFO)\s+[A-Z][A-Z0-9]+-\d+\s+\d+\s")


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _first_errors(text, limit=5, context=2):
    """First real (non-benign) error lines, each with a little context."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if not _ERR_LINE.search(line) or _SUMMARY_ROW.match(line):
            continue
        m = _CODE.search(line)
        if m and m.group(1) in BENIGN_ERROR_CODES:
            continue
        # A Python traceback's useful line is its LAST line ("FooError: ...").
        if line.strip().startswith("Traceback"):
            continue
        if re.match(r"^\w+(Error|Exception)\b:", line.strip()):
            lo, hi = max(0, i - context), i + 1          # traceback: show where it came from
        else:
            lo, hi = i, min(len(lines), i + context + 1)  # tool error: show what follows
        snippet = "\n".join(l.rstrip()[:300] for l in lines[lo:hi]).strip("\n")
        out.append(snippet)
        if len(out) >= limit:
            break
    return out


def _stage_eval(obj_dir, action_result):
    """Run Nour's evaluate_stage for one syn/par action the loop ran."""
    stage = action_result["action"]
    tool_log = os.path.join(obj_dir, f"{stage}-rundir", TOOL_LOGS[stage])
    driver_log = action_result["log"]
    log = tool_log if os.path.isfile(tool_log) else driver_log
    # The loop's hammer_stage writes -o <obj_dir>/<action>-output.json.
    out_json = os.path.join(obj_dir, f"{stage}-output.json")
    ev = evaluate_stage(log_path=log, output_json_path=out_json, stage=stage,
                        exit_code=action_result["rc"])
    # Hammer-side (Python) errors and license failures land in the driver log.
    drv = condense_log(_read(driver_log))
    if drv["infrastructure_failure"]:
        ev["status"] = "infrastructure_failure"
    ev["logs"] = {"tool": tool_log if os.path.isfile(tool_log) else None,
                  "driver": driver_log}
    return ev


def _rung(obj_dir, stage_evals, driver_text):
    j = lambda *p: os.path.join(obj_dir, *p)
    rung = 0
    if "Loaded Sky130 Tech" in driver_text or os.path.isdir(j("syn-rundir")):
        rung = 1
    if stage_evals.get("syn", {}).get("status") == "passed":
        rung = 2
    # Hammer's Innovus flow saves pre_<step> checkpoints; place_pins runs right
    # after power_straps, so its checkpoint means floorplan + straps succeeded.
    if rung >= 2 and (glob.glob(j("par-rundir", "pre_place_pins*"))
                      or glob.glob(j("par-rundir", "pre_place_opt_design*"))):
        rung = 3
    if stage_evals.get("par", {}).get("status") == "passed":
        rung = 4
    return rung


def evaluate(obj_dir: str, run_result: dict) -> dict:
    actions = run_result.get("actions", [])
    stage_evals = {a["action"]: _stage_eval(obj_dir, a)
                   for a in actions if a["action"] in TOOL_LOGS}
    driver_text = "\n".join(_read(a["log"]) for a in actions)
    rung = _rung(obj_dir, stage_evals, driver_text)

    if any(e["status"] == "infrastructure_failure" for e in stage_evals.values()) \
            or condense_log(driver_text)["infrastructure_failure"]:
        status = "infra_error"
    elif run_result.get("ok") and stage_evals and \
            all(e["status"] == "passed" for e in stage_evals.values()):
        status = "pass"
    else:
        status = "fail"

    failed = next((a["action"] for a in actions if a["rc"] != 0), None)
    if failed is None:
        failed = next((s for s, e in stage_evals.items() if e["status"] != "passed"), None)

    # Errors the agent should look at: from the failing stage's logs, or all logs.
    focus = [a for a in actions if a["action"] == failed] or actions
    err_text = ""
    for a in focus:
        err_text += _read(a["log"]) + "\n"
        tl = os.path.join(obj_dir, f"{a['action']}-rundir", TOOL_LOGS.get(a["action"], "-"))
        err_text += _read(tl) + "\n"
    first_errors = _first_errors(err_text)

    all_codes = {}
    for e in stage_evals.values():
        for code, n in e["diagnostics"]["errors"].items():
            all_codes[code] = all_codes.get(code, 0) + n
    new_codes = {c: n for c, n in all_codes.items() if c not in BENIGN_ERROR_CODES}
    missing = [m for e in stage_evals.values() for m in e["artifacts"]["missing_artifacts"]]

    if status == "infra_error":
        summary = ("rung={} status=infra_error: license/infrastructure failure -- "
                   "not caused by the config; retry later.").format(rung)
    else:
        summary = f"rung={rung} status={status}"
        if failed:
            summary += f" failed_stage={failed}"
        if new_codes:
            summary += " error_codes=" + ",".join(f"{c}x{n}" for c, n in sorted(new_codes.items()))
        if missing:
            summary += f" missing_outputs={missing[:5]}"
        if first_errors and status != "pass":
            summary += "\nfirst errors:\n" + "\n---\n".join(first_errors[:3])

    return {
        "rung": rung,
        "status": status,
        "failed_action": failed,
        "summary": summary,
        "first_errors": first_errors if status != "pass" else [],
        "error_codes": new_codes,
        "benign_error_codes": {c: n for c, n in all_codes.items() if c in BENIGN_ERROR_CODES},
        "missing_artifacts": missing,
        "stages": stage_evals,          # Nour's full per-stage output
    }


def _run_result_from_dir(obj_dir):
    """Rebuild a run_result from the <action>.chia.log files hammer_stage wrote."""
    actions = []
    for action in ("syn", "syn-to-par", "par"):
        log = os.path.join(obj_dir, f"{action}.chia.log")
        if not os.path.isfile(log):
            continue
        out = os.path.join(obj_dir, f"{action}-output.json")
        actions.append({"action": action, "rc": 0 if os.path.isfile(out) else 1,
                        "seconds": None, "log": log})
    return {"actions": actions, "ok": bool(actions) and all(a["rc"] == 0 for a in actions)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python evaluator_adapter.py <obj_dir>")
    d = sys.argv[1]
    r = evaluate(d, _run_result_from_dir(d))
    print(r["summary"])
    print(json.dumps({k: v for k, v in r.items() if k != "stages"}, indent=2, default=str))
