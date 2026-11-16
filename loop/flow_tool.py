"""FlowTool -- lets the agent test its own edits mid-turn (start / poll).

Same pattern as CHIA's timing_opt `timing_experiment` tool: a flow run can
outlast an MCP HTTP round-trip, so `start()` returns a job id immediately and
`status()` polls it.

Each run works on a SNAPSHOT copy of the agent's workspace taken at start()
time, in its own scratch build dir (<branch>/trials/tN/), so the agent can keep
editing while a run is in flight. Runs go through the same `run_stage` CHIA node
as the loop's official run, so they queue on the head's single VLSI slot (shared
licenses). These trial runs never count as the branch's result -- the driver's
own run after the agent finishes is the official score.

The tool server lives on the head (head_tools resource). Its state lives in the
server actor; a jobs.json in trials_dir mirrors it for the driver to read.
"""
import json
import os
import shutil
import time

from chia.base.tools.ChiaTool import ChiaTool

STAGE_HELP = {
    "build": "seconds; loads Hammer + the tech plugin (paths, PDK files). Passing = rung 1.",
    "syn": "~1 min for GCD; Genus synthesis. Passing = rung 2.",
    "par": "~5 min for GCD; synthesis then Innovus place-and-route. Passing = rung 4.",
}


class FlowTool(ChiaTool):
    def setup(self, workspace: str, trials_dir: str, max_runs: int = 10,
              max_wait_cap: int = 120):
        self.workspace = os.path.realpath(workspace)
        self.trials_dir = trials_dir
        self.max_runs = max_runs
        self.max_wait_cap = max_wait_cap
        n = self.name
        self.mcp.add_tool(self.start, name=f"{n}_start")
        self.mcp.add_tool(self.status, name=f"{n}_status")
        self.mcp.add_tool(self.list_jobs, name=f"{n}_list_jobs")
        self.mcp.add_tool(self.cancel, name=f"{n}_cancel")

    # ---- state (lazy, so it is created inside the server actor) -----------
    def _ensure(self):
        if not hasattr(self, "_jobs"):
            self._jobs, self._refs = {}, {}

    def _save(self):
        os.makedirs(self.trials_dir, exist_ok=True)
        tmp = os.path.join(self.trials_dir, "jobs.json.tmp")
        with open(tmp, "w") as f:
            json.dump(self._jobs, f, indent=2, default=str)
        os.replace(tmp, os.path.join(self.trials_dir, "jobs.json"))

    # ---- tools (docstrings are what the agent sees) -----------------------
    def start(self, stage: str) -> str:
        """Start a flow run on a SNAPSHOT of your current workspace and return a
        job id immediately. stage is one of:
          "build" - seconds; loads Hammer + the tech plugin (paths, PDK files) -> rung 1
          "syn"   - ~1 min; Genus synthesis -> rung 2
          "par"   - ~5 min; synthesis then Innovus place-and-route -> rung 4
        Poll with status(job_id). Runs are queued one at a time (shared licenses)
        and there is a per-turn budget, so check cheaply ("build") before "syn"/"par".
        Edits you make after start() do not affect a run already started."""
        self._ensure()
        from hammer_stage import run_stage
        if stage not in STAGE_HELP:
            return f"ERROR: stage must be one of {list(STAGE_HELP)}"
        if len(self._jobs) >= self.max_runs:
            return (f"ERROR: run budget used up ({self.max_runs} runs this turn). "
                    "Finish your turn with a summary; the loop will do the official run.")
        jid = f"t{len(self._jobs) + 1}"
        root = os.path.join(self.trials_dir, jid)
        ws, obj = os.path.join(root, "workspace"), os.path.join(root, "build")
        if os.path.exists(root):
            shutil.rmtree(root)
        shutil.copytree(self.workspace, ws)
        os.makedirs(obj)
        self._refs[jid] = run_stage.chia_remote(stage, ws, obj)
        self._jobs[jid] = {"stage": stage, "state": "queued_or_running",
                           "started": time.time(), "obj_dir": obj}
        self._save()
        return (f"{jid} started (stage={stage}: {STAGE_HELP[stage]}). "
                f"Runs used: {len(self._jobs)}/{self.max_runs}. Poll with status(\"{jid}\").")

    def status(self, job_id: str, max_wait_seconds: int = 60) -> str:
        """Wait up to max_wait_seconds (max 120) for a job, then report. Returns
        'still running' or the evaluation: rung, pass/fail, first real errors, and
        log paths you can open with the ws read/grep tools."""
        import ray
        self._ensure()
        job = self._jobs.get(job_id)
        if job is None:
            return f"ERROR: unknown job '{job_id}'. Known: {list(self._jobs)}"
        if job["state"] != "queued_or_running":
            return job.get("report", f"{job_id}: {job['state']}")
        ready, _ = ray.wait([self._refs[job_id]],
                            timeout=max(1, min(int(max_wait_seconds), self.max_wait_cap)))
        if not ready:
            return (f"{job_id} ({job['stage']}): still queued/running after "
                    f"{time.time() - job['started']:.0f}s. Call status again.")
        try:
            run = ray.get(ready[0])
        except Exception as e:                                  # worker died / cancelled
            job.update(state="error", report=f"{job_id}: run errored: {e!r}"[:2000])
            self._save()
            return job["report"]
        from evaluator_adapter import evaluate
        ev = evaluate(job["obj_dir"], run)
        logs = [a["log"] for a in run["actions"]]
        tool_logs = [p for p in (os.path.join(job["obj_dir"], "syn-rundir", "genus.log"),
                                 os.path.join(job["obj_dir"], "par-rundir", "innovus.log"))
                     if os.path.isfile(p)]
        report = (f"{job_id} ({job['stage']}) finished after "
                  f"{time.time() - job['started']:.0f}s\n{ev['summary']}\n"
                  f"hammer logs: {logs}\ntool logs: {tool_logs}")
        job.update(state="done", rung=ev["rung"], status=ev["status"],
                   finished=time.time(), report=report)
        self._save()
        return report

    def list_jobs(self) -> dict:
        """List this turn's runs with their stage, state, rung and status."""
        self._ensure()
        return {j: {k: v for k, v in d.items() if k != "report"} for j, d in self._jobs.items()}

    def cancel(self, job_id: str) -> str:
        """Cancel a queued/running job you no longer need (frees the license slot)."""
        import ray
        self._ensure()
        if job_id not in self._refs:
            return f"ERROR: unknown job '{job_id}'"
        if self._jobs[job_id]["state"] == "queued_or_running":
            ray.cancel(self._refs[job_id], force=True)
            self._jobs[job_id]["state"] = "cancelled"
            self._save()
        return f"{job_id}: {self._jobs[job_id]['state']}"
