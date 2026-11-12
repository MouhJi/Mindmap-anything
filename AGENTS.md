Repository Guidelines
Project Structure & Module Organization
- crawler/: asynchronous crawling and extraction; standalone Markdown cleaning in crawler/cleaning/.
- knowledge/: structured extraction, normalization, evidence validation, graph expansion, Neo4j persistence, and the read API. Cypher migrations live in knowledge/migrations/.
- frontend/: independent React/TypeScript/Vite demo; components, services, and sample data are under src/, static assets under public/, and tests under tests/.
- tests/: Python tests. scripts/verify_cleaning.py validates saved crawl fixtures.
- docs/ and evaluation/: architecture notes and evaluation tooling. output/page*.json contains regression fixtures; preserve these originals. Edit source packages rather than generated build/ copies.
Build, Test, and Development Commands
Use Python 3.11+ and Node.js 22.18+.
- python -m pip install -e ".[test]": install the Python package and pytest; add the graph extra for Neo4j support.
- playwright install chromium: install the browser required for crawling.
- docs-crawl https://fastapi.tiangolo.com/ --max-pages 10 --output-dir output/local: crawl into a separate directory.
- python -m pytest -q: run Python tests from the repository root.
- python -m scripts.verify_cleaning: check preservation and idempotency; write results under output/cleaned/.
- python -m knowledge.evaluation --output output/graph-quality/evaluation.json: evaluate the labeled synthetic sample offline.
- Inside `frontend/`, use pnpm 11.25.0 as pinned in `package.json`. Run `pnpm install --frozen-lockfile`, then `pnpm dev` for local development, `pnpm test` for service tests, or `pnpm build` for TypeScript checking and production assets.
Coding Style & Naming Conventions
Use four-space Python indentation, type hints, snake_case functions/modules, and PascalCase classes. Ruff configuration specifies a 100-character line length; no formatter is enforced. Frontend code uses two-space indentation, single quotes, omitted semicolons, PascalCase component filenames, and camelCase functions. Preserve strict TypeScript checks and existing module boundaries.
Testing Guidelines
Python uses pytest with tests/test_*.py files and test_* functions. Frontend tests use Node's built-in runner in frontend/tests/*.test.ts. Add regressions for changed behavior; no numeric coverage threshold is configured. Live Neo4j tests require GRAPH_TEST_NEO4J=1 and NEO4J_* credentials. For UI changes, check desktop/mobile layouts and keyboard interaction.
Commit & Pull Request Guidelines
Git history uses informal summaries without a prefix scheme. Write concise, imperative subjects describing one change. PRs should explain behavior, link relevant issues, record validation commands/results, and include screenshots for UI changes. Keep unrelated generated artifacts out of changes.
Security & Configuration
Keep database credentials and provider keys in environment variables, never browser code or committed files. Preserve explicit mock provenance in the frontend; its default service does not crawl URLs or call the Python API.
Agent Workflow Requirements
1. Select an Appropriate Model for Each Request
After reading each request, assess its complexity, scope, and correctness requirements. When the environment exposes model selection, automatically choose an available model and reasoning effort appropriate to the task, balancing quality, latency, and cost. Prefer a lightweight model for straightforward edits and a stronger reasoning model for architecture, complex debugging, or changes across multiple modules. Respect explicit user model preferences. If model switching is unavailable, continue with the current model and do not claim that a switch occurred. This rule does not itself authorize spawning additional agents.
2. Review the Completed Task and Remove Unnecessary Files
After implementation, review the complete diff for correctness, regressions, scope, and consistency with repository conventions. Run the checks appropriate to the changed behavior and fix issues found during review. Remove temporary scripts, scratch files, duplicate outputs, and disposable artifacts created during the task when they are no longer needed. Before deleting any other file, verify that it is obsolete, unreferenced, and within the requested scope. Preserve pre-existing user changes, original regression fixtures, required tests, migrations, configuration, and evaluation evidence. If a file's purpose is uncertain, keep it and report the uncertainty. Avoid broad cleanup commands that can remove unrelated work. Rerun affected checks if cleanup changes executable code or required assets.
3. Update Relevant Markdown Documentation
After review and cleanup, update the Markdown files affected by the final implementation, such as README.md, relevant files in docs/ or evaluation/, and AGENTS.md when repository guidance changes. Document actual behavior, setup and commands, configuration variable names without secrets, API or schema changes, and known limitations where relevant. Update existing documentation before creating a new file, and leave unrelated Markdown files unchanged. Do not claim that checks passed unless they were run successfully. Review documentation examples against the final implementation, then finish with a concise summary of changes, validation results, and any unresolved limitations. If no documentation changes are needed, state that briefly in the completion summary.
