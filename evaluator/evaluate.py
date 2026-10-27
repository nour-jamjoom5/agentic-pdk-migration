import json
from pathlib import Path

from evaluator.condense_log import condense_log

def verify_artifacts(output_json_path, stage):
    with Path(output_json_path).open() as f:
        outputs = json.load(f)

    required_keys = {
        "syn": [
            "synthesis.outputs.output_files",
            "synthesis.outputs.sdc",
        ],
        "par": [
            "par.outputs.output_gds",
            "par.outputs.output_netlist",
            "par.outputs.def_file",
        ],
    }

    missing = []

    for key in required_keys[stage]:
        paths = outputs.get(key, [])
        if isinstance(paths, str):
            paths = [paths]

        if not paths:
            missing.append(key)
            continue

        for path in paths:
            if not path or path == "None":
                missing.append(key)
                continue

            artifact = Path(path)
            if not artifact.is_file() or artifact.stat().st_size == 0:
                missing.append(str(artifact))

    return {
        "complete": len(missing) == 0,
        "missing_artifacts": missing,
    }

def evaluate_stage(log_path, output_json_path, stage, exit_code):
    log_text = Path(log_path).read_text(
        encoding="utf-8", errors="replace"
    )

    diagnostics = condense_log(log_text)
    artifacts = verify_artifacts(output_json_path, stage)

    if diagnostics["infrastructure_failure"]:
        status = "infrastructure_failure"
    elif exit_code == 0 and artifacts["complete"]:
        status = "passed"
    else:
        status = "failed"

    return {
        "status": status,
        "stage": stage,
        "exit_code": exit_code,
        "artifacts": artifacts,
        "diagnostics": diagnostics,
    }
