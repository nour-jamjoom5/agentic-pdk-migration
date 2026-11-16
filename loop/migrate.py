"""Driver for the agentic PDK-migration loop (structure follows chia/examples/timing_opt).

Milestone 2 (implemented): --seed-only
    Stage the workspace template as branch "seed", run Hammer (syn or par) on the head
    through CHIA, evaluate, and record it in the DB. No agent. This is the
    GCD/open-PDK baseline reproduced through CHIA.

Milestones 3-4: --iterations N  -- agent edits a child workspace through the
    sandboxed WorkspaceTool (agent.py / workspace_tool.py), the driver re-runs
    the flow, evaluates, records; stops at --target-rung.

Usage (on eda-1, after `chia up loop/cluster.eda1.yaml`):
    cd loop
    python migrate.py --seed-only --stage syn
    python migrate.py --seed-only --stage par --force   # re-seed through P&R
    python migrate.py --list
    # milestone 4 (known-answer test: broken sky130A path):
    MIG_RUNS_DIR=/scratch/cs199-aau/pdk-migration/runs_ka python migrate.py \\
        --template known_answer_template --prompt prompts/known_answer.md \\
        --stage syn --iterations 3 --target-rung 2
    # flow-tool test: two faults that only show up one after the other
    # (bad PDK path breaks "build"; once fixed, a bad Genus path breaks "syn").
    # With the flow tool the agent should fix both in ONE turn; with
    # --no-flow-tool it needs two rounds.
    MIG_RUNS_DIR=/scratch/cs199-aau/pdk-migration/runs_2f python migrate.py \\
        --template two_faults_template --prompt prompts/known_answer.md \\
        --stage syn --iterations 3 --target-rung 2
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
if os.environ.get("MIG_EVALUATOR", "nour") == "stub":
    from eval_stub import evaluate                    # placeholder (no repo-root deps)
else:
    from evaluator_adapter import evaluate            # Nour's evaluator/ via the adapter
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


def _log_tail(branch, n=60):
    try:
        ev = json.loads(branch["eval_json"] or "{}")
        logs = [a["log"] for a in ev.get("run", {}).get("actions", [])]
        if not logs:
            return "(no log)"
        with open(logs[-1], errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except Exception as e:
        return f"(could not read log: {e})"


FLOW_HELP = """You can run the flow yourself with the `flow_*` tools (they run on a
snapshot of your workspace and report rung, pass/fail and the first real errors):
  flow_start("build") - seconds; checks Hammer + the tech plugin load (rung 1)
  flow_start("syn")   - ~1 min; synthesis (rung 2)
  flow_start("par")   - ~5 min; synthesis + place-and-route (rung 4)
then poll flow_status(job_id). You have {max_runs} runs this turn, queued one at a time on
shared licenses: check cheaply with "build" first, and fix errors one by one until
the target stage passes. Open full logs with the ws read/grep tools when the summary
is not enough. When you are done (or out of runs), end with a short summary; the
loop then does the official run."""

NO_FLOW_HELP = ("You cannot run the flow yourself this turn; it is re-run automatically "
                "after you finish.")


def iterate(db, parent, stage, n, prompt_path, model, target_rung,
            use_flow_tool=True, max_trial_runs=None):
    """One parent -> child pass: stage child ws; agent edits it through the sandboxed
    WorkspaceTool and (optionally) tests its edits with FlowTool; driver re-runs the
    flow (authoritative), evaluates, records."""
    from agent import agent_turn
    from flow_tool import FlowTool
    from workspace_tool import WorkspaceTool

    max_trial_runs = max_trial_runs or config.MAX_TRIAL_RUNS
    child = f"{parent.split('_v')[0]}_v{n}"
    while db.get(child):
        n += 1
        child = f"{parent.split('_v')[0]}_v{n}"
    pb = db.get(parent)
    ws, obj = stage_workspace(child, parent, db)
    trials = str(Path(ws).parent / "trials")
    os.makedirs(trials, exist_ok=True)

    prompt = Path(prompt_path).read_text().format(
        workspace_files="\n".join(sorted(os.listdir(ws))),
        stage=stage,
        last_eval=json.dumps({k: v for k, v in
                              json.loads(pb["eval_json"] or "{}").get("eval", {}).items()
                              if k != "stages"}, indent=2),   # drop Nour's full per-stage dump
        log_tail=_log_tail(pb),
        flow_help=(FLOW_HELP.format(max_runs=max_trial_runs) if use_flow_tool
                   else NO_FLOW_HELP),
    )
    tools = [WorkspaceTool(name="ws", workspace=ws,
                           # the agent may also read its own trial runs' logs
                           read_only_roots=config.READ_ONLY_ROOTS + [trials],
                           deny_substrings=config.DENY_SUBSTRINGS,
                           task_options={"resources": {"head_tools": 1}})]
    if use_flow_tool:
        tools.append(FlowTool(name="flow", workspace=ws, trials_dir=trials,
                              max_runs=max_trial_runs,
                              task_options={"resources": {"head_tools": 1}}))
    print(f"[{child}] agent turn (parent={parent}, rung={pb['rung']}, "
          f"flow_tool={'on, %d runs' % max_trial_runs if use_flow_tool else 'off'})")
    try:
        turn = get(agent_turn.chia_remote(prompt, tools, model, config.LLM_TIMEOUT_S,
                                          f"mig_{child}"))
    finally:
        # Stopping the FlowTool server also tears down any trial run it still owns.
        for t in tools:
            t.stop()
    Path(ws).parent.joinpath("agent_reply.md").write_text(turn["result"])
    trial_jobs = {}
    if os.path.exists(os.path.join(trials, "jobs.json")):
        trial_jobs = json.loads(Path(trials, "jobs.json").read_text())
        for j, d in trial_jobs.items():
            print(f"  trial {j}: stage={d['stage']:<5} state={d['state']:<17} "
                  f"rung={d.get('rung')} status={d.get('status')}")
    print(f"[{child}] agent success={turn['success']} trial_runs={len(trial_jobs)}: "
          f"{turn['result'][-600:]}")

    db.add(child, parent, stage, ws, obj)
    print(f"[{child}] official run: hammer stage '{stage}'")
    run = get(run_stage.chia_remote(stage, ws, obj))
    ev = evaluate(obj, run)
    db.finish(child, ev["status"], ev["rung"],
              {"run": run, "eval": ev, "trials": trial_jobs}, agent_log=turn["result"])
    print(f"[{child}] {ev['summary']}")
    return ev


def main():
    global TEMPLATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-run the seed")
    ap.add_argument("--stage", choices=["syn", "par"], default="syn")
    ap.add_argument("--list", action="store_true", help="print the branch table and exit")
    ap.add_argument("--template", default=str(TEMPLATE),
                    help="seed workspace dir (e.g. known_answer_template for milestone 4)")
    ap.add_argument("--iterations", type=int, default=1)
    ap.add_argument("--prompt", default=str(HERE / "prompts" / "task.md"))
    ap.add_argument("--model", default=config.LLM_MODEL)
    ap.add_argument("--no-flow-tool", action="store_true",
                    help="agent can't run the flow itself (one blind edit per round)")
    ap.add_argument("--max-trial-runs", type=int, default=config.MAX_TRIAL_RUNS,
                    help="FlowTool runs the agent may start per turn")
    ap.add_argument("--target-rung", type=int, default=2,
                    help="stop once a branch reaches this rung (2 = syn, 4 = par)")
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
             runtime_env={"working_dir": str(HERE), "excludes": ["__pycache__"],
                          # Nour's evaluator/ lives at the repo root; ship it to workers
                          # (FlowTool evaluates trial runs inside its server actor).
                          "py_modules": [str(HERE.parent / "evaluator")]},
             ignore_reinit_error=True)

    TEMPLATE = Path(args.template)
    seed(db, args.stage, force=args.force)
    if args.seed_only:
        s = db.get("seed")
        return 0 if s and s["status"] == "pass" else 1

    for i in range(1, args.iterations + 1):
        best = db.best()
        if best and best["rung"] is not None and best["rung"] >= args.target_rung \
                and best["status"] == "pass":
            print(f"target rung {args.target_rung} reached by '{best['name']}' -- stopping")
            break
        ev = iterate(db, best["name"] if best else "seed", args.stage, i,
                     args.prompt, args.model, args.target_rung,
                     use_flow_tool=not args.no_flow_tool,
                     max_trial_runs=args.max_trial_runs)
        if ev["status"] == "infra_error":
            print("infra error (license/disk/timeout) -- stopping; rerun later")
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
