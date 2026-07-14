---
description: "Investigate a codebase and draft or update AGENTS.md for future agent sessions. Covers project identity, build/run/test commands, config system, module structure, gotchas, and code style."
---

# Draft AGENTS.md

Create or update `AGENTS.md` for the repository at `$ARGUMENTS` (default: current working directory).

The goal is a compact instruction file that helps future agent sessions avoid mistakes and ramp up quickly. Every line must answer: **"Would an agent likely miss this without help?"** If not, leave it out.

## Investigation order

Read the highest-value sources first:

1. **Identity**: `README*`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle*`, or any root manifest
2. **Build & tooling**: lockfiles, build scripts, CI config (`.github/`, `.gitlab-ci.yml`, `Makefile`, `justfile`, `Taskfile*`)
3. **Quality gates**: linter, formatter, typechecker, test runner configs (`.eslintrc*`, `ruff.toml`, `tsconfig*`, `jest.config*`, `pytest.ini`, `tox.ini`)
4. **Entry points**: `main.*`, `index.*`, `cmd/`, `app/`, or whatever the runtime entry is
5. **Structure**: top-level directory layout, key modules/packages
6. **Conventions**: `.editorconfig`, existing style guides, naming patterns observed in source

## Output sections (include only when relevant)

- **Project overview** — one paragraph max
- **Key commands** — install, build, run, test, lint, format
- **Module structure** — brief map of what lives where
- **Config system** — how configuration works, hot reload, env vars
- **Gotchas** — easy-to-miss traps, platform constraints, ordering dependencies
- **Code style** — formatter, naming conventions, import style
- **Testing** — how to run tests, what's covered, what's manual

## Rules

- Keep it short. Prefer bullets over prose.
- Exclude generic software advice, long tutorials, obvious language conventions.
- Exclude anything the agent could trivially discover by reading a file.
- If the repo already has an `AGENTS.md`, read it first and only update what's stale or missing.
- Write in the same language as the user's primary working language (check recent commits or existing docs for cues).
