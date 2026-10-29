# agentic-pdk-migration
An agentic loop, built on [CHIA](https://chialoops.ai), that migrates a Hammer design from the **open SKY130 PDK** (Google/SkyWater) to the **Cadence SKY130 PDK** without a human writing the migration.

Both PDKs target the same SkyWater 130nm process but ship different files, so the agent has to rework the Hammer setup: switch to the Cadence standard cells (`sky130_scl`), point at the Cadence tech files, fix power straps, and later handle SRAMs, I/O cells, power-on reset, and level shifters.

A hand-done reference migration exists, but **the agent never sees it**. We only use it afterward to compare.

## How the loop works

```
[Agent node]    Claude Code edits the tech plugin / YAML (sandboxed)
     │
     ▼
[Hammer node]   runs one flow stage with the Cadence tools
     │
     ▼
[Evaluate node] our code, no AI: condense logs, score which rung was reached
     │
     └──► errors + rung go back to the Agent node
```

## Evaluator ladder
Each run is scored by how far the design gets through the flow. Each step is a **rung**; a run's score is the highest rung it passes
1. Tech plugin loads
2. Synthesis completes
3. Floorplan + power straps succeed
4. Place-and-route completes
5. DRC count (non-waived rules)
6. LVS clean

Later: Rocket, SRAMs, I/O ring, power-on reset, level shifters.

## Rules

- **Keep the reference out.** No reference slides, hooks, or configs in this repo or the agent's workspace. Existing tapeout Chipyard checkouts (e.g. `ucb-eecs151tapeout`) and CHIA's `examples/sky130_vlsi` already contain the answer, so don't give them to the agent.
- **Use upstream Hammer** (`ucb-bar/hammer` master), per Jim. No pin. (The last commit before Cadence SKY130 support predates Hammer's Pegasus DRC/LVS plugin, so a pinned agent could never reach rungs 5–6.)
- **No web access** for the agent.
- **Don't commit** PDK files, logs, or tool outputs.
- **Cap concurrent runs.** Machines and licenses are shared.

## Environment

Work on `eda-#.eecs.berkeley.edu` in `/scratch/<your-login>` (not backed up, so push often). Licenses are automatic. CHIA runs from the `chia_env` conda environment.

| Tool | Path | Version |
| ---- | ---- | ------- |
| Genus | `/share/instsww/cadence/GENUS231/bin/genus` | 23.18 (tested) |
| Innovus | `/share/instsww/cadence/INNOVUS231/bin/innovus` | 23.18 (tested: GCD place-and-route) |
| Pegasus | `/share/instsww/cadence/PEGASUS-25.13.000/bin/pegasus` | 25.13 (tested) |

PDKs are in `/home/ff/ee198/ee198-20/sky130_col/`: Cadence PDK `sky130_release_0.0.9`, std cells `sky130_scl_9T_0.1.2`, open PDK `open_pdks-2022.10`, SRAMs `sram22_sky130_macros`.

## Plan

| # | Step | Status |
| - | ---- | ------ |
| 1 | Run Hammer's GCD example on open SKY130 by hand (baseline) | ✅ Done: rungs 1–4 pass. See `baseline/NOTES.md` |
| 2 | Get a skeleton CHIA loop running on eda-1 (agent node + Hammer node) | ✅ Done: working end to end. See `loop/README.md` |
| 3 | Write the evaluate node (log condenser + ladder) | 🟡 In progress |
| 4 | Write the task spec; point the agent at rung 1 | ⬜ Not started |
| 5 | Let it climb and record where it gets stuck | ⬜ Waiting on 3 + 4 |

## Who's doing what

| Area | Owner | Status |
| ---- | ----- | ------ |
| Repo + environment | Nour | ✅ Done |
| Baseline GCD run | Sid | ✅ Done (`baseline/`) |
| CHIA loop skeleton | Sid | ✅ Done (`loop/`). Known-answer test passed |
| Evaluate node | Nour | 🟡 In progress (log condenser). Must match `evaluate(obj_dir, run_result)` in `loop/eval_stub.py` |
| Task spec + agent config | TBD | ⬜ Goes in `loop/prompts/task.md` |

Claim a task in Slack before starting.

## Notes so far

- CHIA is installed in `chia_env` on eda-1 and hello-world works.
- Hammer (upstream) is installed into `chia_env` with `pip install -e .`.
- **How the loop is laid out** (details in `loop/README.md`):
  - Hammer and the Cadence tools run directly on eda-1 (the head node).
  - Claude runs in a podman container with no access to our files. It can only use a workspace tool that:
    - reads and writes its own work folder
    - reads the PDKs and Hammer's source
    - refuses everything else
- The head allows one flow run at a time (shared licenses).
- The Claude container uses the login in `/scratch/cs199-aau/claude_config_dir/.claude`, which is a personal account. We should ask about a lab API key.
- 2026-10-20: the license server (`license-srv:5280`) was unreachable from eda-1/eda-2 for one night. If Genus fails with `Cannot obtain … license`, it's an infrastructure problem, not our config.

## Open questions
- What version string does Hammer expect for Pegasus 25.13 (likely `"2513"` or `"251"`)?
- Should the agent be able to read Hammer's built-in `sky130_cds` support? (Currently yes, since Jim said "use upstream". To hide it, add `"sky130_cds"` to `DENY_SUBSTRINGS` in `loop/config.py`.)
- DRC/LVS on the open-PDK side: Magic/Netgen aren't installed on eda-1. Do we only score rungs 5–6 after migration, with Pegasus?
