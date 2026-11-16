# Your workspace

Everything here is yours to edit (read + write). Each flow run uses exactly these files.

| Path | What it is | How Hammer gets it |
|---|---|---|
| `env.yml` | Environment: tool binaries/versions, license servers, PDK locations | `-e env.yml` |
| `overrides.yml` | Project settings; loaded after the base PDK/tool/design configs, so it wins | `-p overrides.yml` |
| `configs/*.yml` | (optional) more settings files you create; loaded after `overrides.yml`, in name order | `-p` each |
| `hooks.py` | Python hook lists (`SYN_HOOKS`, `PAR_HOOKS`, `DRC_HOOKS`, `LVS_HOOKS`) that insert/replace/remove tool steps, usually by appending Tcl | loaded by the loop's driver |
| `tcl/` | (optional) Tcl snippets for your hooks; read them with paths relative to `hooks.py` | via `hooks.py` |
| `agent_tech/sky130/` | **Your own copy of Hammer's SKY130 technology plugin** (Python + `defaults.yml` + `sky130.tech.json`). Used because `overrides.yml` sets `vlsi.core.technology: "agent_tech.sky130"`. Settings keep the `technology.sky130.*` names. | imported from this workspace |

Fixed (not in your workspace, read-only): the base configs in Hammer's `e2e/`
(`configs-pdk/sky130.yml`, `configs-tool/cm.yml`, `configs-design/gcd/*`) and the
Hammer source itself. You can read them to learn which settings exist
(`hammer/*/defaults.yml`, tool plugins' `__init__.py`).

Rules:
- Prefer settings (`env.yml`, `overrides.yml`, `configs/`) over code; change
  `hooks.py` or `agent_tech/sky130/` when settings can't do it.
- Only reference files under your allowed roots (see `ws_allowed_roots`), using
  absolute paths there or paths relative to this workspace. **A run is blocked
  (`ERROR [guard]`) if any file here references another absolute path or a known
  reference-flow name.**
- Python/Tcl errors in your files show up in the run log like any other error.
