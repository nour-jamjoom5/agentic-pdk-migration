import subprocess
from pathlib import Path
from evaluator.evaluate import evaluate_stage

def run_command(command, working_dir, log_path):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("w") as log_file:
        result = subprocess.run(
            command,
            cwd=working_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )

    return {
        "exit_code": result.returncode,
        "log_path": str(log_path),
    }

def get_output_json(build_dir, stage):
    if stage not in ("syn", "par"):
        raise ValueError(f"Unsupported Hammer stage: {stage}")

    output_path = Path(build_dir) / f"{stage}-rundir" / f"{stage}-output.json"

    return output_path

def get_tool_log(build_dir, stage):
    log_names = {
        "syn": "genus.log",
        "par": "innovus.log",
    }

    if stage not in log_names:
        raise ValueError(f"Unsupported Hammer stage: {stage}")

    return Path(build_dir) / f"{stage}-rundir" / log_names[stage]

def build_hammer_command(stage, build_dir):
    if stage not in ("build", "syn", "par"):
        raise ValueError(f"Unsupported Hammer stage: {stage}")

    return [
        "make",
        "design=gcd",
        "pdk=sky130",
        "tools=cm",
        "env=eda",
        "extra=configs-env/eda-open-signoff.yml",
        f"OBJ_DIR={Path(build_dir).resolve()}",
        stage,
    ]

def run_hammer(stage, build_dir, command, working_dir, log_path):
    if stage not in ("syn", "par"):
        raise ValueError(f"Unsupported Hammer stage: {stage}")

    output_json = get_output_json(build_dir, stage)
    tool_log = get_tool_log(build_dir, stage)

    # Remove previous stage metadata to avoid stale results.
    if output_json.exists():
        output_json.unlink()

    if tool_log.exists():
        tool_log.unlink()

    # Execute Hammer and capture its actual exit code.
    result = run_command(command, working_dir, log_path)

    # Prefer detailed tool diagnostics when available.
    diagnostic_log = (
        tool_log if tool_log.is_file() else result["log_path"]
    )

    evaluation = evaluate_stage(
        log_path=diagnostic_log,
        output_json_path=output_json,
        stage=stage,
        exit_code=result["exit_code"],
    )

    return {
        "stage": stage,
        "exit_code": result["exit_code"],
        "log_path": result["log_path"],
        "tool_log_path": str(tool_log) if tool_log.is_file() else None,
        "output_json": str(output_json),
        "output_json_exists": output_json.is_file(),
        "evaluation": evaluation,
    }
def run_hammer_build(build_dir, working_dir, log_path):
    command = build_hammer_command("build", build_dir)

    return run_command(
        command=command,
        working_dir=working_dir,
        log_path=log_path,
    )
