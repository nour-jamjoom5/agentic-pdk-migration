"""The agent node: one Claude Code turn on the llm_1 container (same pattern as
timing_opt's improve_timing_llm). The container can't see the host; the agent
acts only through the ChiaTools passed in."""
import os

from chia.base.ChiaFunction import ChiaFunction

LLM_ENV = "/home/ray/llm_env"        # created by run_setup_commands in the cluster yaml
LOG_DIR = "/tmp/ray/llm_logs"


@ChiaFunction(resources={"claude_creds": 0.01}, max_retries=0)
def agent_turn(prompt: str, tools: list, model: str, timeout_seconds: int,
               logging_name: str) -> dict:
    from chia.models.claude import ClaudeCodeLLM
    os.makedirs(LLM_ENV, exist_ok=True)
    os.chdir(LLM_ENV)
    os.makedirs(LOG_DIR, exist_ok=True)
    llm = ClaudeCodeLLM(
        model=model,
        timeout_seconds=timeout_seconds,
        log_dir=LOG_DIR,
        logging_name=logging_name,
        # README rule: no web access for the agent.
        extra_cli_args=["--disallowedTools", "WebFetch,WebSearch"],
    )
    r = llm.prompt(prompt, tools)
    return {"success": r.success, "result": r.result or "",
            "returncode": getattr(r, "returncode", None)}
