You are maintaining a Hammer VLSI flow (Cadence Genus/Innovus) for a small GCD
design on the SKY130 process. The flow configuration lives in your workspace:
`env.yml` (environment: tool paths, licenses, PDK locations) and `overrides.yml`.
The last flow run failed. Fix the workspace configuration so that the requested
stage succeeds. Make the smallest correct change.

Rules:
- Use only the `ws_*` tools. Call `ws_allowed_roots` first to see where you may look.
- You can only write inside your workspace. Do not try to run the flow yourself;
  it is re-run automatically after you finish.
- End with a short summary of what you changed and why.

Workspace files:
{workspace_files}

Result of the last flow run (stage: {stage}):
{last_eval}

Tail of the failing log:
{log_tail}
