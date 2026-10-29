"""Milestone 1: is the cluster healthy?

  - head:  VLSI worker can see hammer, Genus/Innovus, the PDKs, the license server
  - llm_1: Claude Code answers a trivial prompt (credentials + container OK)

Run on eda-1 after `chia up loop/cluster.eda1.yaml`:
    cd loop && python smoke.py            # or: chia job submit --working-dir . -- python smoke.py
"""
import os
import socket
import sys
from pathlib import Path

import ray
from chia.base.ChiaFunction import ChiaFunction, get

HERE = Path(__file__).resolve().parent


@ChiaFunction(resources={"VLSI": 1}, max_retries=0)
def head_check() -> dict:
    import shutil
    import config
    paths = {
        "hammer_bin": config.HAMMER_BIN,
        "genus": "/share/instsww/cadence/GENUS231/bin/genus",
        "innovus": "/share/instsww/cadence/INNOVUS231/bin/innovus",
        "open_pdk": "/home/ff/ee198/ee198-20/sky130_col/open_pdks-2022.10/share/pdk/sky130A",
        "cadence_pdk": "/home/ff/ee198/ee198-20/sky130_col/sky130_release_0.0.9",
    }
    out = {"host": socket.gethostname(), "hammer-vlsi": shutil.which("hammer-vlsi")}
    out.update({k: os.path.exists(v) for k, v in paths.items()})
    try:
        socket.create_connection(("license-srv.eecs.berkeley.edu", 5280), timeout=5).close()
        out["license_port_5280"] = "open"
    except OSError as e:
        out["license_port_5280"] = f"UNREACHABLE ({e})"
    return out


@ChiaFunction(resources={"claude_creds": 0.01}, max_retries=0)
def llm_hello(model: str) -> dict:
    from chia.models.claude import ClaudeCodeLLM
    os.makedirs("/home/ray/llm_env", exist_ok=True)
    os.chdir("/home/ray/llm_env")
    os.makedirs("/tmp/ray/llm_logs", exist_ok=True)
    llm = ClaudeCodeLLM(model=model, timeout_seconds=300,
                        log_dir="/tmp/ray/llm_logs", logging_name="smoke")
    r = llm.prompt("Reply with exactly the text CHIA_OK and nothing else.", [])
    # Also prove the sandbox: the container must NOT see the host's PDK tree.
    return {"host": socket.gethostname(), "success": r.success,
            "reply": (r.result or "")[:200],
            "sees_host_pdk_dir": os.path.exists("/home/ff/ee198")}


def main():
    ray.init(address=os.environ.get("RAY_ADDRESS", "auto"),
             runtime_env={"working_dir": str(HERE), "excludes": ["__pycache__"]},
             ignore_reinit_error=True)
    model = sys.argv[1] if len(sys.argv) > 1 else "claude-sonnet-4-6"
    print("head_check:", get(head_check.chia_remote()))
    print("llm_hello :", get(llm_hello.chia_remote(model)))


if __name__ == "__main__":
    main()
