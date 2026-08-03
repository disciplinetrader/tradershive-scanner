# Repository Guidelines

## Project Structure & Module Organization

This repository is currently a clean scaffold: no application source, tests, or build configuration have been committed. Keep the root focused on project-wide files such as `README.md`, dependency manifests, and tool configuration. As the project grows, use predictable top-level directories:

- `src/` for production code, grouped by feature or domain.
- `tests/` for automated tests that mirror the layout of `src/`.
- `assets/` for static files such as fixtures, images, or sample data.
- `scripts/` for repeatable development and maintenance tasks.

Avoid committing generated output, local caches, credentials, or editor-specific files. Add them to `.gitignore` when the relevant tooling is introduced.

## Build, Test, and Development Commands

No build system or package manager is configured yet. When adding one, expose a small, documented set of commands through the ecosystem's standard task runner. Prefer conventional entry points such as:

- `npm run dev` to start a local development process.
- `npm test` to run the complete automated test suite.
- `npm run lint` to perform static checks.
- `npm run build` to create a production artifact.

Update this guide and `README.md` in the same change that introduces or replaces these commands.

## Coding Style & Naming Conventions

Adopt the standard formatter and linter for the chosen language, commit their configuration, and run them before submitting changes. Use consistent indentation; do not mix tabs and spaces. Favor descriptive names: `PascalCase` for types and components, `camelCase` for functions and variables, and `kebab-case` for general file names unless the language ecosystem dictates otherwise. Keep modules focused and avoid unrelated refactors in feature changes.

## Testing Guidelines

Every behavior change should include tests once a test framework is selected. Mirror source paths in `tests/`, and name tests after the behavior under test (for example, `scanner-filters.test.ts`). Cover successful paths, invalid input, and boundary cases. Bug fixes should include a regression test that fails without the fix.

## Commit & Pull Request Guidelines

There is no existing commit history to establish a repository-specific convention. Use short, imperative commit subjects, optionally following Conventional Commits, such as `feat: add market scanner` or `fix: reject invalid symbols`.

Pull requests should explain the problem and solution, list verification commands, and link relevant issues. Include screenshots or sample output for user-visible changes. Keep each pull request scoped, ensure checks pass, and call out configuration changes or follow-up work explicitly.
