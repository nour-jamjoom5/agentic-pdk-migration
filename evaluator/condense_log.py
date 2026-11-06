import argparse
import json
import re
from collections import Counter
from pathlib import Path


def condense_log(log_text):
    pattern = re.compile(
        r"\b(ERROR|WARNING|WARN)\s*:?\s*\(([A-Z][A-Z0-9]+-\d+)\)",
        re.IGNORECASE,
    )

    errors = Counter()
    warnings = Counter()

    for match in pattern.finditer(log_text):
        severity = match.group(1).upper()
        code = match.group(2)

        if severity == "ERROR":
            errors[code] += 1
        else:
            warnings[code] += 1

    license_failure = bool(
        re.search(
            r"Cannot obtain .* license|license.*(?:timeout|timed out)",
            log_text,
            re.IGNORECASE,
        )
    )

    return {
        "errors": dict(errors),
        "warnings": dict(warnings),
        "infrastructure_failure": license_failure,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Condense Hammer tool logs")
    parser.add_argument("logfile", help="Path to a log file")
    args = parser.parse_args()

    log_text = Path(args.logfile).read_text(
        encoding="utf-8", errors="replace"
    )
    print(json.dumps(condense_log(log_text), indent=2))
