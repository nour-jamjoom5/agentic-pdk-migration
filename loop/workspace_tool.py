"""WorkspaceTool -- the ONLY way the agent touches eda-1.

The agent itself runs in the llm_1 container (it cannot see the host). This MCP
tool server runs on the HEAD, so it can reach the PDKs, but it enforces:
  * read + write : the branch's workspace dir only
  * read-only    : an allowlist of roots (Cadence PDK, open PDK, Hammer source, ...)
  * refused      : everything else (reference flows, other users, tapeout checkouts),
                   plus anything matching DENY_SUBSTRINGS
Paths are resolved with realpath first, so symlinks / ".." can't escape.
"""
import fnmatch
import os
import re

from chia.base.tools.ChiaTool import ChiaTool

MAX_READ = 40_000          # chars per read_file call
MAX_GREP_HITS = 200
MAX_WRITE = 200_000


class WorkspaceTool(ChiaTool):
    def setup(self, workspace: str, read_only_roots=(), deny_substrings=()):
        self.workspace = os.path.realpath(workspace)
        self.ro_roots = [os.path.realpath(r) for r in read_only_roots]
        self.deny = list(deny_substrings)
        n = self.name
        self.mcp.add_tool(self.list_dir, name=f"{n}_list_dir")
        self.mcp.add_tool(self.read_file, name=f"{n}_read_file")
        self.mcp.add_tool(self.grep, name=f"{n}_grep")
        self.mcp.add_tool(self.write_file, name=f"{n}_write_file")
        self.mcp.add_tool(self.replace_in_file, name=f"{n}_replace_in_file")
        self.mcp.add_tool(self.allowed_roots, name=f"{n}_allowed_roots")

    # ---- access control -------------------------------------------------
    def _resolve(self, path: str, write: bool = False) -> str:
        p = path if os.path.isabs(path) else os.path.join(self.workspace, path)
        real = os.path.realpath(p)
        if any(d in real for d in self.deny):
            raise PermissionError(f"refused: {path} is outside what you may access")
        under = lambda root: real == root or real.startswith(root + os.sep)
        if under(self.workspace):
            return real
        if not write and any(under(r) for r in self.ro_roots):
            return real
        raise PermissionError(
            f"refused: {path} is outside your workspace"
            + ("" if write else " and the read-only roots"))

    # ---- tools (docstrings are what the agent sees) ----------------------
    def allowed_roots(self) -> dict:
        """Return the directories you may access: 'workspace' (read+write; relative
        paths resolve here) and 'read_only' (PDKs and tool sources you may read)."""
        return {"workspace": self.workspace, "read_only": self.ro_roots}

    def list_dir(self, path: str = ".", max_entries: int = 500) -> str:
        """List a directory (non-recursive). Dirs end with '/'. Relative paths are
        inside your workspace."""
        try:
            real = self._resolve(path)
            names = sorted(os.listdir(real))[:max_entries]
            return "\n".join(n + ("/" if os.path.isdir(os.path.join(real, n)) else "")
                             for n in names) or "(empty)"
        except Exception as e:
            return f"ERROR: {e}"

    def read_file(self, path: str, offset: int = 0, max_chars: int = MAX_READ) -> str:
        """Read a text file starting at character `offset` (max ~40k chars per call;
        call again with a larger offset to continue). Use grep first on huge files
        like .lib / .lef."""
        try:
            real = self._resolve(path)
            with open(real, errors="replace") as f:
                f.seek(0, 2); size = f.tell(); f.seek(offset)
                data = f.read(min(max_chars, MAX_READ))
            more = offset + len(data) < size
            return data + (f"\n[... truncated; file is {size} chars, next offset "
                           f"{offset + len(data)}]" if more else "")
        except Exception as e:
            return f"ERROR: {e}"

    def grep(self, pattern: str, path: str, file_glob: str = "*",
             max_hits: int = 100) -> str:
        """Regex-search a file, or every file matching `file_glob` under a directory
        (recursive). Returns 'file:line: text' hits (capped)."""
        try:
            real = self._resolve(path)
            rx = re.compile(pattern)
            files = [real] if os.path.isfile(real) else [
                os.path.join(d, f) for d, _, fs in os.walk(real) for f in fs
                if fnmatch.fnmatch(f, file_glob)]
            hits = []
            for fp in files:
                try:
                    self._resolve(fp)
                    with open(fp, errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if rx.search(line):
                                hits.append(f"{fp}:{i}: {line.rstrip()[:300]}")
                                if len(hits) >= min(max_hits, MAX_GREP_HITS):
                                    return "\n".join(hits) + "\n[... hit cap]"
                except (PermissionError, OSError):
                    continue
            return "\n".join(hits) or "(no matches)"
        except Exception as e:
            return f"ERROR: {e}"

    def write_file(self, path: str, content: str) -> str:
        """Create or overwrite a file INSIDE your workspace (relative path)."""
        try:
            if len(content) > MAX_WRITE:
                return "ERROR: content too large"
            real = self._resolve(path, write=True)
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with open(real, "w") as f:
                f.write(content)
            return f"wrote {len(content)} chars to {os.path.relpath(real, self.workspace)}"
        except Exception as e:
            return f"ERROR: {e}"

    def replace_in_file(self, path: str, old: str, new: str) -> str:
        """Replace exactly one occurrence of `old` with `new` in a workspace file.
        Fails if `old` is missing or appears more than once."""
        try:
            real = self._resolve(path, write=True)
            with open(real) as f:
                s = f.read()
            n = s.count(old)
            if n != 1:
                return f"ERROR: `old` found {n} times (must be exactly 1)"
            with open(real, "w") as f:
                f.write(s.replace(old, new))
            return "ok"
        except Exception as e:
            return f"ERROR: {e}"
