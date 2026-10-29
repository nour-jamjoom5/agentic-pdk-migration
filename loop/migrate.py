"""Driver for the agentic PDK-migration loop (structure follows chia/examples/timing_opt).

Milestone 2 (implemented): --seed-only
    Stage the workspace template as branch "seed", run Hammer (syn or par) on the head
    through CHIA, evaluate, and record it in the DB. No agent. This is the
    GCD/open-PDK baseline reproduced through CHIA.

Milestones 3-4 (TODO, see iterate()): agent edits a child workspace through a
    sandboxed WorkspaceTool, the driver re-runs the flow, evaluates, records.

Usage (on eda-1, after `chia up loop/cluster.eda1.yaml`):
    cd loop
    python migrate.py --seed-only --stage syn
    python migrate.py --seed-only --stage par --force   # re-seed through P&R
    python migrate.py --list
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import ray
from chia.base.ChiaFunction import get

import config
from db import MigrationDB
from eval_stub import evaluate          # TODO: swap for Nour's evaluator (same interface)
from hammer_stage import run_stage

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "workspace_template"


def _branch_dirs(name):
    root = Path(config.RUNS_DIR) / name
    return root / "workspace", root / "build"


def stage_workspace(name, parent=None, db=None):
    """Create <runs>/<name>/workspace as a copy of the parent's workspace
    (or the template for the seed). Returns (workspace_dir, obj_dir)."""
    ws, obj = _branch_dirs(name)
    if ws.parent.exists():
        shutil.rmtree(ws.parent)
    src = Path(db.get(parent)["workspace_dir"]) if parent else TEMPLATE
    shutil.copytree(src, ws)
    obj.mkdir(parents=True)
    return str(ws), str(obj)


def run_and_record(db, name, parent, stage):
    ws, obj = stage_workspace(name, parent, db)
    db.add(name, parent, stage, ws, obj)
    print(f"[{name}] running hammer stage '{stage}' (workspace={ws})")
    try:
        run = get(run_stage.chia_remote(stage, ws, obj))
    except Exception as e:                      # worker/ray failure, not a flow failure
        db.finish(name, "error", None, {"exception": repr(e)})
        raise
    ev = evaluate(obj, run)
    db.finish(name, ev["status"], ev["rung"], {"run": run, "eval": ev})
    for a in run["actions"]:
        print(f"  {a['action']:<11} rc={a['rc']:<4} {a['seconds']:>7.1f}s  log={a['log']}")
    print(f"[{name}] {ev['summary']}")
    return ev


def seed(db, stage, force=False):
    if db.has_any() and not force:
        print("DB already seeded (use --force to re-run the seed).")
        return db.get("seed")
    if force and db.get("seed"):
        db.conn.execute("DELETE FROM branches WHERE name='seed'")
        db.conn.commit()
    return run_and_record(db, "seed", None, stage)


def iterate(db, parent, stage, iteration):
    """One parent -> child pass. TODO (milestones 3-4):
      1. child = f"{parent}_v{iteration}"; stage_workspace(child, parent)
      2. ws_tool = WorkspaceTool(name="ws", workspace=child_ws,
             read_only_roots=[Cadence PDK, open PDK, hammer src],
             task_options={"resources": {"VLSI": 0.001}})       # server on the head
      3. get(agent_turn.chia_remote(prompt.format(last_eval=...), [ws_tool]))  # llm_1
      4. run_and_record(db, child, parent, stage)   (authoritative run + eval)
      5. ws_tool.stop(); keep best rung; retry on infra_error; stop on rung target
    """
    raise NotImplementedError("agent iteration lands in milestone 3-4")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-run the seed")
    ap.add_argument("--stage", choices=sorted(config.STAGES), default="syn")
    ap.add_argument("--list", action="store_true", help="print the branch table and exit")
    ap.add_argument("--ray-address", default=os.environ.get("RAY_ADDRESS", "auto"))
    args = ap.parse_args()

    os.makedirs(config.RUNS_DIR, exist_ok=True)
    db = MigrationDB(config.DB_PATH)

    if args.list:
        for b in db.all():
            print(f"{b['name']:<20} parent={b['parent'] or '-':<12} stage={b['stage']:<4} "
                  f"status={b['status']:<12} rung={b['rung']}")
        return 0

    ray.init(address=args.ray_address,
             runtime_env={"working_dir": str(HERE), "excludes": ["__pycache__"]},
             ignore_reinit_error=True)

    ev = seed(db, args.stage, force=args.force)
    if args.seed_only:
        return 0 if ev and ev.get("status") == "pass" else 1
    best = db.best()
    return 0 if iterate(db, best["name"], args.stage, 1) else 1


if __name__ == "__main__":
    sys.exit(main())
