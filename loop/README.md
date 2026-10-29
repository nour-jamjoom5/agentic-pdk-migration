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
| `eval_stub.py` | Placeholder evaluator (`evaluate(obj_dir, run) -> {rung, status, summary}`); replace with `evaluator/` |
| `db.py` | SQLite branch tree (`parent → child`), like `timing_opt/db.py` |
| `migrate.py` | Driver: seed, then `--iterations N` agent passes until `--target-rung` |
| `agent.py` | `agent_turn` — one Claude Code turn on `llm_1` (web tools disabled) |
| `workspace_tool.py` | `WorkspaceTool` MCP server on the head: r/w workspace, read-only PDK/Hammer roots, refuses everything else (symlink/`..`-safe) |
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
chia down cluster.eda1.yaml
```
Runs land in `/scratch/cs199-aau/pdk-migration/runs/<branch>/{workspace,build}` (+ `migration.db`).

## Milestones
1. ✅ verified — cluster up, `smoke.py` passes, container can't see `/home/ff`
2. ✅ syn verified (rung 2, 38 s) / ⬜ par — `--seed-only` reproduces the GCD baseline
3. ✅ code / ⬜ verified — `WorkspaceTool` (read/write workspace, read-only PDK roots, refuse everything else) + agent turn
4. ✅ code / ⬜ verified — loop on a known-answer task (break `sky130A` path in the template → agent fixes → rung 0→2)
5. ⬜ real task spec + Nour's evaluator
