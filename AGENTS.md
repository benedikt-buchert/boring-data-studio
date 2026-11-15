# Agent entry

Data Studio connector for the Boring Semantic Layer. Research in `research/docs/research.md` (section 7.8 = live evidence); spike in `prototype/`.

Before touching BSL expressions, read `docs/bsl-gotchas.md`.
Before driving Data Studio or Apps Script through the Chrome MCP, read `docs/datastudio-driving.md`.
To run the API, expose it and replay fixtures: `docs/dev-loop.md`. `make check` is the gate.

## Agent skills

### Issue tracker

GitHub Issues on benedikt-buchert/boring-data-studio (`gh` locally, GitHub MCP in cloud sessions). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` and `docs/adr/` (created on demand). See `docs/agents/domain.md`.
