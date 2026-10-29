"""Paths and knobs for the migration loop. Override any of these with env vars
(pass them via `chia job submit --runtime-env-json '{"env_vars": {...}}'`, since
Ray jobs do NOT inherit your shell)."""
import os

# Hammer checkout on eda-1 (upstream ucb-bar/hammer, installed -e into chia_env)
HAMMER_E2E = os.environ.get(
    "MIG_HAMMER_E2E", "/scratch/cs199-aau/pdk-migration/hammer/e2e")
# The hammer CLI the stage node runs. e2e/example-driver = what the baseline used.
HAMMER_BIN = os.environ.get("MIG_HAMMER_BIN", os.path.join(HAMMER_E2E, "example-driver"))

# Where every branch's workspace + build dir lives (on the head, /scratch is per-machine)
RUNS_DIR = os.environ.get("MIG_RUNS_DIR", "/scratch/cs199-aau/pdk-migration/runs")
DB_PATH = os.environ.get("MIG_DB_PATH", os.path.join(RUNS_DIR, "migration.db"))

# Fixed (non-agent-editable) configs, passed with -p before the workspace's own files.
# Paths are relative to HAMMER_E2E. Design = GCD to start.
BASE_CONFIGS = [
    "configs-pdk/sky130.yml",
    "configs-tool/cm.yml",
    "configs-design/gcd/common.yml",
    "configs-design/gcd/sky130.yml",
]

# Agent-editable workspace files. env.yml is passed with -e, the rest with -p, in this order.
WORKSPACE_ENV = "env.yml"
WORKSPACE_CONFIGS = ["overrides.yml"]

# Stage plan: hammer actions run in order; each stops the chain on failure.
STAGES = {
    "syn": ["syn"],
    "par": ["syn", "syn-to-par", "par"],
}

STAGE_TIMEOUT_S = int(os.environ.get("MIG_STAGE_TIMEOUT_S", 3 * 3600))
# Shared EECS licenses: one flow run at a time (VLSI resource advertised = 1 on head).

# ---- agent sandbox (WorkspaceTool) ----
SKY130_COL = "/home/ff/ee198/ee198-20/sky130_col"
READ_ONLY_ROOTS = [
    f"{SKY130_COL}/sky130_release_0.0.9",          # Cadence PDK (migration target)
    f"{SKY130_COL}/sky130_scl_9T_0.1.2",           # Cadence std cells
    f"{SKY130_COL}/open_pdks-2022.10",             # open PDK (migration source)
    f"{SKY130_COL}/sram22_sky130_macros",
    os.path.join(os.path.dirname(HAMMER_E2E), "hammer"),   # Hammer python pkg + plugins
    HAMMER_E2E,                                    # e2e configs (read-only)
]
# Substrings that are refused even inside allowed roots. Jim said "use upstream"
# Hammer, so its sky130_cds code is NOT hidden by default; add "sky130_cds" here
# if the team decides the agent shouldn't see it.
DENY_SUBSTRINGS = []

LLM_MODEL = os.environ.get("MIG_LLM_MODEL", "claude-sonnet-4-6")
LLM_TIMEOUT_S = int(os.environ.get("MIG_LLM_TIMEOUT_S", 3600))
