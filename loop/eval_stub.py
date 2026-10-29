"""PLACEHOLDER evaluator -- replace with Nour's evaluator (same interface).

evaluate(obj_dir, run_result) -> {"rung", "status", "summary", ...}
Rungs (README ladder): 1 tech loads, 2 syn, 3 floorplan+straps, 4 par, 5 DRC, 6 LVS.
"""
import glob
import os
import re

INFRA_PATTERNS = [
    r"Cannot obtain '.*' license",
    r"No space left on device",
    r"timed out after \d+s",
]


def _read_tail(path, n=200):
    try:
        with open(path, errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []


def evaluate(obj_dir: str, run_result: dict) -> dict:
    j = lambda *p: os.path.join(obj_dir, *p)
    rung = 0
    logs = [a["log"] for a in run_result.get("actions", [])]
    text = "".join("".join(_read_tail(l, 400)) for l in logs)

    if "Loaded Sky130 Tech" in text or os.path.isdir(j("syn-rundir")):
        rung = 1
    if os.path.exists(j("syn-output.json")) and glob.glob(j("syn-rundir", "*.mapped.v")):
        rung = 2
    # Hammer's Innovus flow saves pre_<step> checkpoints; place_pins runs right after
    # power_straps, so its checkpoint existing means floorplan + straps succeeded.
    if glob.glob(j("par-rundir", "pre_place_pins*")) or glob.glob(j("par-rundir", "pre_place_opt_design*")):
        rung = 3
    if os.path.exists(j("par-output.json")) and glob.glob(j("par-rundir", "*.gds")):
        rung = 4

    for pat in INFRA_PATTERNS:
        if re.search(pat, text):
            return {"rung": rung, "status": "infra_error",
                    "summary": f"Infrastructure failure matched /{pat}/ -- retry later, not an agent error."}

    status = "pass" if run_result.get("ok") else "fail"
    first_err = next((l.strip() for l in text.splitlines()
                      if re.search(r"\*\*ERROR|^Error|Traceback|Exception", l)), "")
    failed = next((a["action"] for a in run_result.get("actions", []) if a["rc"] != 0), None)
    summary = f"rung={rung} status={status}"
    if failed:
        summary += f" failed_action={failed} first_error: {first_err[:500]}"
    return {"rung": rung, "status": status, "failed_action": failed,
            "first_error": first_err[:2000], "summary": summary}
