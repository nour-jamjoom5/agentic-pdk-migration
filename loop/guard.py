"""Reference guard: block a flow run if the agent's workspace points outside the
allowed folders.

Why: the agent can now write Python (hooks.py, its tech-plugin copy) and Tcl that
Hammer runs on the HEAD, outside the container. That code could read files the
WorkspaceTool would refuse (e.g. the reference flow). The rule "the agent never
sees the reference" is a fairness rule for the experiment, so before every run
(trial or official) we scan the workspace's text files for absolute paths and
known reference names, and refuse to run if any falls outside the allowlist.

This is a tripwire, not a security boundary: it reads text, so a path built at
runtime (string concatenation, env tricks) would slip through. Files in
agent_tech/ that are still identical to upstream Hammer are skipped.
"""
import filecmp
import os
import re

import config

# An absolute path: starts a token (after whitespace/quote/=/bracket/comma/colon)
# and has at least one path component. "${...}/x" and "https://" don't match.
_ABS_PATH = re.compile(
    r"""(?:(?<=^)|(?<=[\s"'=(\[{,:;]))(/[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*)""",
    re.MULTILINE)
MAX_BYTES = 2_000_000


def _allowed_prefixes():
    return [os.path.realpath(p) for p in
            config.READ_ONLY_ROOTS + [config.RUNS_DIR] + config.GUARD_EXTRA_ALLOWED]


def _under(path, prefixes):
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def _pristine(workspace, fpath):
    """True if fpath is an untouched copy of the upstream SKY130 plugin."""
    rel = os.path.relpath(fpath, os.path.join(workspace, "agent_tech", "sky130"))
    if rel.startswith(".."):
        return False
    up = os.path.join(config.SKY130_PLUGIN_SRC, rel)
    return os.path.isfile(up) and filecmp.cmp(fpath, up, shallow=False)


def check(workspace: str, max_report: int = 20):
    """Return a list of violation strings ('file:line: reason'); empty = OK."""
    workspace = os.path.realpath(workspace)
    allowed = _allowed_prefixes() + [workspace]
    deny = config.GUARD_DENY_SUBSTRINGS + config.DENY_SUBSTRINGS
    out = []
    for d, dirs, files in os.walk(workspace):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git")]
        for fn in files:
            fp = os.path.join(d, fn)
            rel = os.path.relpath(fp, workspace)
            try:
                if os.path.getsize(fp) > MAX_BYTES:
                    continue
                with open(fp, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if b"\0" in data or _pristine(workspace, fp):
                continue
            text = data.decode("utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                for s in deny:
                    if s and s in line:
                        out.append(f"{rel}:{i}: mentions forbidden reference '{s}'")
                for m in _ABS_PATH.finditer(line):
                    p = m.group(1)
                    if not _under(os.path.normpath(p), allowed):
                        out.append(f"{rel}:{i}: path outside allowed roots: {p}")
                if len(out) >= max_report:
                    return out
    return out
