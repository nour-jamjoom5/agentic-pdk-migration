# loop/ — CHIA loop skeleton

```
eda-1 HEAD (bare metal, chia_env, VLSI=1)                llm_1 (container, claude_creds)
  migrate.py driver                                        ClaudeCodeLLM
   ├─ seed: template workspace → run_stage → evaluate      sees ONLY the MCP tools we pass:
   └─ iterate (TODO): stage child ws → agent turn ──────►    ws  (WorkspaceTool, server on head)
                      → run_stage → evaluate → DB
```

| File | What |
|---|---|
| `cluster.eda1.yaml` | Head (Hammer + Cadence tools, `VLSI: 1` = one flow run at a time) + `llm_1` Claude Code container |
| `config.py` | Paths (Hammer e2e dir, runs dir, DB) and stage plan; override via `MIG_*` env vars |
| `hammer_stage.py` | `run_stage(stage, workspace_dir, obj_dir)` — `@ChiaFunction` on `VLSI`, runs `syn` / `syn → syn-to-par → par` |
| `evaluator_adapter.py` | **Default evaluator.** Wraps Nour's `evaluator/` (repo root): runs her `evaluate_stage` per Hammer stage, maps it to rungs, filters the known-harmless error codes, and extracts the first real error lines for the agent. Re-score any build dir: `python evaluator_adapter.py <obj_dir>` |
| `eval_stub.py` | Old placeholder evaluator; use with `MIG_EVALUATOR=stub` |
| `db.py` | SQLite branch tree (`parent → child`), like `timing_opt/db.py` |
| `migrate.py` | Driver: seed, then `--iterations N` agent passes until `--target-rung` |
| `agent.py` | `agent_turn` — one Claude Code turn on `llm_1` (web tools disabled) |
| `agent_driver.py` | The Hammer driver every run uses (replaces `e2e/example-driver`): same thing, but its extra hooks come from the workspace's `hooks.py`. Not agent-editable |
| `guard.py` | **Reference guard**, checked before every run (trial and official): blocks the run (`ERROR [guard]`) if any workspace file mentions an absolute path outside the allowed roots or a known reference-flow name. Needed because agent-written Python/Tcl runs on the head, outside the container. A tripwire, not a security boundary (it reads text) |
| `workspace_common/` | Added to every seed workspace: `hooks.py` (starts as the baseline's hooks: remove `place_bumps`) and `WORKSPACE.md` (the agent's guide to its workspace; injected into the prompt as `{workspace_guide}`) |
| `flow_tool.py` | `FlowTool` (`flow_start` / `flow_status` / `flow_list_jobs` / `flow_cancel`): the agent runs `build` (seconds, rung 1), `syn` or `par` on a **snapshot** of its workspace mid-turn and gets the evaluator's summary back. Budget `--max-trial-runs` (default 10) per turn; runs queue on the head's single VLSI slot; never counts as the official score. Off with `--no-flow-tool` |
| `workspace_tool.py` | `WorkspaceTool` MCP server on the head: r/w workspace, read-only PDK/Hammer roots, refuses everything else (symlink/`..`-safe) |
| `two_faults_template/` | Flow-tool test: bad PDK path **and** bad Genus path; the second only shows up after the first is fixed |
| `known_answer_template/`, `prompts/known_answer.md` | Milestone 4 test: seed with a broken `sky130A` path; the agent must fix it |
| `smoke.py` | Milestone 1 health check (head tools/licenses + Claude in the container) |
| `workspace_template/` | Seed workspace (agent-editable later): `env.yml` (`-e`), `overrides.yml` (`-p`, last) |
| `prompts/task.md` | Placeholder — owned by the task-spec person |

## Run it (on eda-1)
```bash
conda activate chia_env
cd <repo>/loop
chia up cluster.eda1.yaml          # head + llm_1 container
python smoke.py                    # milestone 1
python migrate.py --seed-only --stage syn     # milestone 2 (≈1 min)
python migrate.py --seed-only --stage par --force   # full baseline through P&R (≈5 min)
python migrate.py --list
# milestone 4: known-answer test (separate runs dir so it doesn't touch the real DB)
MIG_RUNS_DIR=/scratch/cs199-aau/pdk-migration/runs_ka python migrate.py \
    --template known_answer_template --prompt prompts/known_answer.md \
    --stage syn --iterations 3 --target-rung 2
# flow-tool test (two sequential faults; expect both fixed in one agent turn)
MIG_RUNS_DIR=/scratch/cs199-aau/pdk-migration/runs_2f python migrate.py \
    --template two_faults_template --prompt prompts/known_answer.md \
    --stage syn --iterations 3 --target-rung 2
chia down cluster.eda1.yaml
```
Runs land in `/scratch/cs199-aau/pdk-migration/runs/<branch>/{workspace,build}` (+ `migration.db`).

## The agent's workspace (what it may edit)
Each seed workspace = template (`env.yml`, `overrides.yml`) + `hooks.py` + `WORKSPACE.md` + **`agent_tech/sky130/`, the agent's own copy of Hammer's SKY130 tech plugin** (copied from the installed Hammer; selected by `vlsi.core.technology: "agent_tech.sky130"` in `overrides.yml`; settings keep their `technology.sky130.*` names). The agent may also add `configs/*.yml` (loaded after `overrides.yml`) and `tcl/` snippets for its hooks. `MIG_AGENT_TECH_PLUGIN=0` turns the plugin copy off.

## Milestones
1. ✅ verified — cluster up, `smoke.py` passes, container can't see `/home/ff`
2. ✅ verified — `--seed-only --stage par` reproduces the GCD baseline through CHIA: syn 38 s → syn-to-par → par 277 s, rung 4
3. ✅ verified — `WorkspaceTool` (read/write workspace, read-only PDK roots, refuse everything else) + agent turn
4. ✅ verified (2026-10-29) — loop on a known-answer task (break `sky130A` path in the template → agent fixes → rung 0→2)
4b. ⬜ FlowTool: agent fixes two sequential faults in ONE turn (`two_faults_template`)
4c. ⬜ Wider workspace (own tech plugin copy, hooks.py, configs/, guard): seed still reaches rung 4
5. 🟡 Nour's evaluator wired in (`evaluator_adapter.py`) / ⬜ real task spec
