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
- **Pin Hammer** to a commit before Cadence SKY130 support, with `.git` removed. Commit: `TODO`
- **No web access** for the agent.
- **Don't commit** PDK files, logs, or tool outputs.
- **Cap concurrent runs.** Machines and licenses are shared.

## Environment

Work on `eda-#.eecs.berkeley.edu` in `/scratch/<your-login>` (not backed up, so push often). Licenses are automatic. CHIA runs from the `chia_env` conda environment.

| Tool | Path | Version |
| ---- | ---- | ------- |
| Genus | `/share/instsww/cadence/GENUS231/bin/genus` | 23.18 (tested) |
| Innovus | `/share/instsww/cadence/INNOVUS231/bin/innovus` | 23.1 (not yet tested) |
| Pegasus | `/share/instsww/cadence/PEGASUS-25.13.000/bin/pegasus` | 25.13 (tested) |

PDKs are in `/home/ff/ee198/ee198-20/sky130_col/`: Cadence PDK `sky130_release_0.0.9`, std cells `sky130_scl_9T_0.1.2`, open PDK `open_pdks-2022.10`, SRAMs `sram22_sky130_macros`.

## Plan (target: Oct 26)

1. Run Hammer's GCD example on open SKY130 by hand (baseline)
2. Get a skeleton CHIA loop running on eda-1 (agent node + Hammer node)
3. Write the evaluate node (log condenser + ladder)
4. Write the task spec; point the agent at rung 1
5. Let it climb and record where it gets stuck

## Who's doing what

| Area | Owner |
| ---- | ----- |
| Repo + environment | TODO |
| Baseline GCD run | TODO |
| CHIA loop skeleton | TODO |
| Evaluate node | TODO |
| Task spec + agent config | TODO |

Claim a task in Slack before starting.

## Notes so far

- CHIA is installed in `chia_env` on eda-1 and hello-world works.
- CHIA's VLSI workers run directly on the host (no podman), so Hammer can see the Cadence tools, PDKs, and licenses. Podman is only for Chisel/Verilator workers.
- CHIA's `HammerNode.run` needs a worker with a `hammer` resource in `cluster.yaml`.
- Hammer is not installed yet; install upstream `ucb-bar/hammer`.

## Open questions
- What version string does the pinned Hammer expect for Pegasus 25.13 (likely `"2513"` or `"251"`)?
