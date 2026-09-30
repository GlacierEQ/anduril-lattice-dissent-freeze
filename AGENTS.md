# AGENTS.md — anduril-lattice-dissent-freeze

**Company:** Anduril
**Domain:** Command Authority & Mission Assurance

## Quick Rules
- **Test command:** `PYTHONPATH=src pytest tests/ -v`
- **Lint:** `ruff check src/ tests/`
- **No drive-by edits** — load the skill first.

## Architecture
- `src/anduril_lattice_dissent_freeze/core.py` — Domain logic (Command Authority & Mission Assurance)
- `tests/` — Verified test suite
- `.github/workflows/ci.yml` — Enforced CI pipeline
