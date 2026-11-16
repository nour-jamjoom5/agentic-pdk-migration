#!/usr/bin/env python3
"""The Hammer driver every loop run uses. NOT agent-editable (it lives in loop/).

Same as Hammer's e2e/example-driver (what the baseline used), except the extra
hooks come from the agent's workspace: <workspace>/hooks.py may define
SYN_HOOKS, PAR_HOOKS, DRC_HOOKS, LVS_HOOKS, SIM_HOOKS (lists of HammerTool hook
actions). hammer_stage.py sets MIG_WORKSPACE and puts the workspace on
PYTHONPATH, so the workspace's own tech-plugin copy (agent_tech.sky130) imports.
"""
import importlib.util
import os
import sys

from hammer.vlsi import CLIDriver


def _load_workspace_hooks():
    ws = os.environ.get("MIG_WORKSPACE")
    path = os.path.join(ws, "hooks.py") if ws else None
    if not path or not os.path.isfile(path):
        print("[agent_driver] no workspace hooks.py; using no extra hooks", flush=True)
        return None
    spec = importlib.util.spec_from_file_location("workspace_hooks", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # errors here show up in the run log
    counts = {k: len(getattr(mod, k, []) or []) for k in
              ("SYN_HOOKS", "PAR_HOOKS", "DRC_HOOKS", "LVS_HOOKS", "SIM_HOOKS")}
    print(f"[agent_driver] loaded hooks from {path}: {counts}", flush=True)
    return mod


_HOOKS = _load_workspace_hooks()


def _hooks(name):
    return list(getattr(_HOOKS, name, None) or []) if _HOOKS else []


class AgentDriver(CLIDriver):
    def get_extra_synthesis_hooks(self):
        return _hooks("SYN_HOOKS")

    def get_extra_par_hooks(self):
        return _hooks("PAR_HOOKS")

    def get_extra_drc_hooks(self):
        return _hooks("DRC_HOOKS")

    def get_extra_lvs_hooks(self):
        return _hooks("LVS_HOOKS")

    def get_extra_sim_hooks(self):
        return _hooks("SIM_HOOKS")


if __name__ == "__main__":
    AgentDriver().main()
