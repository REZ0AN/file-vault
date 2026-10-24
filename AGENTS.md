# Agent guide

Applies to this repository. Read [rules.md](rules.md) before editing. Use [docs/README.md](docs/README.md) for the architecture and decision guides; when editing the frontend, also follow [frontend/AGENTS.md](frontend/AGENTS.md).

Keep changes focused on the user's request. Preserve the current trust boundaries unless the user asks to change them. If a change alters a boundary, data model, Google scope, or user-visible flow, update the relevant documentation with the code.

Check the affected tests and build before finishing. Report what changed, what was verified, and any remaining limitation.
