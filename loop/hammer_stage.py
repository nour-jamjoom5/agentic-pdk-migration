"""The Hammer node: run one or more hammer-vlsi actions for a workspace.

A plain @ChiaFunction pinned to the head's VLSI resource (Genus/Innovus, licenses
and PDKs live on the eda-1 host, not in a container) -- same pattern as
timing_opt/boom_tile_syn.py. Swap for chia.vlsi.hammer.HammerNode later if we want.
"""
import glob
import os
import subprocess
import sys
import time

from chia.base.ChiaFunction import ChiaFunction

import config
import guard

AGENT_DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_driver.py")


def _hammer_cmd(action, workspace_dir, obj_dir, prev_output):
    driver = [config.HAMMER_BIN] if config.HAMMER_BIN else [sys.executable, AGENT_DRIVER]
    cmd = driver + ["--obj_dir", obj_dir,
           "-e", os.path.join(workspace_dir, config.WORKSPACE_ENV)]
    for c in config.BASE_CONFIGS:
        cmd += ["-p", os.path.join(config.HAMMER_E2E, c)]
    for c in config.WORKSPACE_CONFIGS:
        p = os.path.join(workspace_dir, c)
        if os.path.exists(p):
            cmd += ["-p", p]
    for p in sorted(glob.glob(os.path.join(workspace_dir, config.WORKSPACE_EXTRA_CONFIG_DIR,
                                           "*.yml"))):
        cmd += ["-p", p]
    if prev_output:
        cmd += ["-p", prev_output]          # e.g. syn-output.json feeds syn-to-par
    out_json = os.path.join(obj_dir, f"{action}-output.json")
    cmd += ["-o", out_json, action]
    return cmd, out_json


@ChiaFunction(resources={"VLSI": 1}, max_retries=0)
def run_stage(stage: str, workspace_dir: str, obj_dir: str) -> dict:
    """Run the hammer actions for `stage` ("syn" or "par") on the head.

    Returns {"stage", "obj_dir", "actions": [{action, rc, seconds, log}], "ok"}.
    Logs are written to obj_dir/<action>.chia.log (stdout+stderr of hammer).
    """
    os.makedirs(obj_dir, exist_ok=True)
    results, prev = [], None
    first = config.STAGES[stage][0]

    # Reference guard: refuse to run a workspace that points outside the allowed roots.
    violations = guard.check(workspace_dir)
    if violations:
        log_path = os.path.join(obj_dir, f"{first}.chia.log")
        with open(log_path, "w") as log:
            log.write("ERROR [guard] run blocked: the workspace references files outside "
                      "the allowed folders (PDKs, Hammer source, tool installs, runs dir).\n")
            for v in violations:
                log.write(f"ERROR [guard] {v}\n")
        return {"stage": stage, "obj_dir": obj_dir, "ok": False, "guard": violations,
                "actions": [{"action": first, "rc": -2, "seconds": 0.0, "log": log_path}]}

    # The workspace goes on PYTHONPATH (so its agent_tech.sky130 plugin copy imports)
    # and agent_driver.py reads <workspace>/hooks.py via MIG_WORKSPACE.
    env = dict(os.environ)
    env["PYTHONPATH"] = workspace_dir + (os.pathsep + env["PYTHONPATH"]
                                         if env.get("PYTHONPATH") else "")
    env["MIG_WORKSPACE"] = workspace_dir
    for action in config.STAGES[stage]:
        cmd, out_json = _hammer_cmd(action, workspace_dir, obj_dir, prev)
        log_path = os.path.join(obj_dir, f"{action}.chia.log")
        t0 = time.time()
        with open(log_path, "w") as log:
            log.write("$ " + " ".join(cmd) + "\n\n")
            log.flush()
            try:
                rc = subprocess.run(cmd, cwd=config.HAMMER_E2E, env=env, stdout=log,
                                    stderr=subprocess.STDOUT,
                                    timeout=config.STAGE_TIMEOUT_S).returncode
            except subprocess.TimeoutExpired:
                rc = -9
                log.write(f"\n[chia] {action} timed out after {config.STAGE_TIMEOUT_S}s\n")
        results.append({"action": action, "rc": rc,
                        "seconds": round(time.time() - t0, 1), "log": log_path})
        if rc != 0 or not os.path.exists(out_json):
            return {"stage": stage, "obj_dir": obj_dir, "actions": results, "ok": False}
        prev = out_json
    return {"stage": stage, "obj_dir": obj_dir, "actions": results, "ok": True}
