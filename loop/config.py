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
