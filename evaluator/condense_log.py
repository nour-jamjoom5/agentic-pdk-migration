import re
from collections import Counter


def condense_log(log_text):
    """Extract diagnostic codes and detect license failures."""

    # Matches codes such as TECHLIB-702 and IMPDB-1221.
    error_codes = re.findall(
        r"\b([A-Z][A-Z0-9]+-\d+)\b",
        log_text
    )

    # Detect common license errors.
    license_failure = bool(
        re.search(
            r"Cannot obtain .* license|license.*(?:timeout|timed out)",
            log_text,
            re.IGNORECASE
        )
    )

    return {
        "errors": dict(Counter(error_codes)),
        "infrastructure_failure": license_failure
    }


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Condense Hammer tool logs"
    )
    parser.add_argument("logfile", help="Path to a log file")
    args = parser.parse_args()

    log_text = Path(args.logfile).read_text(
        encoding="utf-8",
        errors="replace"
    )

    result = condense_log(log_text)
    print(json.dumps(result, indent=2))
