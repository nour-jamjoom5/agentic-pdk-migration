# Baseline: GCD on open SKY130 (upstream Hammer, Cadence 23.1 tools)

**Owner:** Sid · **Date:** 2026-10-21 · **Machine:** eda-1 (`/scratch/cs199-aau/pdk-migration`)

The "before" picture the agent starts from: Hammer's GCD example through the flow on the **open** SKY130 PDK, run by hand.

## Result: rungs 1–4 pass, 5–6 not yet run

| Rung | Status | Notes |
|---|---|---|
| 1. Tech plugin loads | ✅ | `make … build` |
| 2. Synthesis | ✅ | Genus 23.18, ~30 s. 260 cells, area 2,529, slack +1,532 ps, 0 failing paths |
| 3. Floorplan + power straps | ✅ | inside `par` |
| 4. Place-and-route | ✅ | Innovus 23.18, ~5 min. 0 unplaced, setup WNS +0.300 ns, hold WNS +0.280 ns, 0 violating paths, 0 DRVs, no route DRC markers. `gcd.gds` written (~9 MB) |
| 5. DRC | ⏸ | Magic not installed on eda-1 (see Open items) |
| 6. LVS | ⏸ | Netgen not installed on eda-1 |

## Setup

- **Hammer:** upstream `ucb-bar/hammer` master (per Jim: "just use upstream" — no pin), `pip install -e .` into `chia_env`.
- **Configs:** `baseline/configs/eda-env.yml` → copy to `hammer/e2e/configs-env/`; `baseline/configs/eda-open-signoff.yml` → same.
  - `tools=cm` sets DRC/LVS to Calibre (Mentor, not in upstream Hammer) — overridden to Magic/Netgen via `extra=`.

```bash
conda activate chia_env
cd <hammer>/e2e
make design=gcd pdk=sky130 tools=cm env=eda extra=configs-env/eda-open-signoff.yml build
make design=gcd pdk=sky130 tools=cm env=eda extra=configs-env/eda-open-signoff.yml syn
make design=gcd pdk=sky130 tools=cm env=eda extra=configs-env/eda-open-signoff.yml par
```
Outputs: `e2e/build-sky130-cm/gcd/{syn,par}-rundir/`.

## Errors seen in a *good* run (evaluator should not treat these as failures)

Innovus PAR reported 29 errors / ~50k warnings and still produced a clean design. All triaged:

| Code | Count | Meaning | Verdict |
|---|---|---|---|
| `TECHLIB-702` | 18 | Open PDK `.lib` bug: `related_bias_pin` refers to missing `VNB` in `lpflow_lsbuf…isowell` (level-shifter) cells | Benign for GCD (no level shifters) |
| `IMPLF-24` | 2 | Open PDK IO LEF defines `VSSIO` twice in `sky130_ef_io__vssa_hvc*_pad` | Benign for GCD (no IO ring) |
| `IMPDB-1221` | 4 | Hammer's generic `vdd`/`vss` global-net-connect patterns match no pins (SKY130 uses `VPWR`/`VGND`, connected by adjacent rules) | Benign |
| `IMPMSMV-3502` | 3 | `VPWR`, `VPB`, `vdd` not assigned to a power domain in CPF | Benign for single-supply design |
| `IMPSP-2002` + `IMPSP-9022` | 1 + 1 | "Density too high (100%)" in late `refinePlace`, after filler insertion | Benign — Unplaced = 0, fillers restored with 0 overlaps |

Note: the benign errors cluster on **level shifters, IO pads, and power domains** — exactly the hard parts of the migration (IO, POR, level shifters). Expect real failures there once the agent moves past GCD.

## Environment failure seen (classify as "infra, retry", not agent error)

- 2026-10-20 ~21:50: `license-srv.eecs.berkeley.edu:5280` unreachable from eda-1 and eda-2. Genus: `Cannot obtain 'Genus_Synthesis' license` after a 40 s timeout per feature; Hammer then raised `find_regs_cells.json not found`. Resolved by the next morning.
- Lesson for the evaluator: the real error is far above the final traceback; match `Cannot obtain .* license` / license timeouts and return "environment broken, retry" instead of feeding it to the agent.

## Gotchas

- `/scratch` is **per machine** — eda-1's scratch doesn't exist on eda-2. Stick to one host or push often.
- The genus `fill_outputs` traceback is a symptom of Genus exiting, never the cause.

## Open items

- [ ] DRC/LVS on the open side: install Magic + Netgen (e.g. conda `litex-hub` channel) **or** decide rungs 5–6 are only meaningful post-migration with Pegasus + Cadence decks.
- [ ] Pegasus version string for Hammer (README open question) — not exercised yet.
- [ ] Share a tarball of `build-sky130-cm/gcd/` logs on eda-1 scratch for the evaluator.
