You are maintaining a Hammer VLSI flow (Cadence Genus/Innovus) for a small GCD
design on the SKY130 process. The flow configuration lives in your workspace:
`env.yml` (environment: tool paths, licenses, PDK locations) and `overrides.yml`.
The last flow run failed. Fix the workspace configuration so that the requested
stage succeeds. There may be more than one problem. Make the smallest correct change.

Rules:
- Use only the `ws_*` tools (and `flow_*` if you have them). Call `ws_allowed_roots` first to see where you may look.
- You can only write inside your workspace.
- {flow_help}
- Before you finish, confirm your fix with the flow tools: run flow_start("build"), then flow_start("{stage}"), and poll flow_status until it passes. If it fails, fix and rerun. Only finish once the requested stage passes.
- End with a short summary of what you changed and why.

Workspace files:
{workspace_files}

Result of the last flow run (stage: {stage}):
{last_eval}

Tail of the failing log:
{log_tail}
