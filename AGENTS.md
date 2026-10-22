# AGENTS.md - MayuriShell

## What this project is
MayuriShell is a customizable command shell for Windows, written in Python. Users type short commands (`spotify`, `projects`, `organize downloads`) to launch apps, open sites and folders, manage files, inspect the system and run workflows. It has a kawaii / Linux-rice visual theme (pastel colors, original animal mascots, fetch-style startup screen).

The full spec is in `SPEC.md`. Hard rules are in `RULES.md` and always apply.

## Project status
- Stages 1 to 7 are complete and v0.1.0 is released.
- New work is done one feature at a time (plan first, wait for approval, build, test, report).

## Tech stack
- Python 3.11+
- rich (output), prompt_toolkit (input, history, tab completion), psutil (system info)
- pathlib, shlex, subprocess, json, logging (standard library)
- pytest (tests)
- PyInstaller (packaging, frozen Windows executable)

No other dependencies unless asked first.

## Project structure
```
MayuriShell/
  main.py
  requirements.txt
  requirements-dev.txt
  README.md
  CHANGELOG.md
  SPEC.md  AGENTS.md  RULES.md
  core/        shell, parser, registry, executor, config_manager,
               history, aliases, logging_config, exceptions, theme,
               completer, mascots, paths, selftest, version
  commands/    appearance, applications, builtins, customization,
               files, navigation, organization, processes,
               project_scaffolding, search, system, websites, workflows
  services/    application_discovery, file_service, launcher_service,
               system_service, workflow_service
  tools/       gen_docs.py
  packaging/   build_installer.bat, build_windows.bat, installer.iss,
               mayurishell.spec, version_info.txt
  docs/        commands.md, configuration.md, packaging.md
  tests/       unit and integration tests (tmp_path only)
```
`core/` must never import from `commands/`. Commands register themselves with the registry. Nothing may depend on `__file__`, the project folder, or the current working directory because the app runs frozen as a PyInstaller executable; use `core/paths.py`.

## How to work
1. **Work one feature at a time.** Plan first, wait for approval, build, test, and report. Do not touch unrelated features or code.
2. **Plan first.** Before writing code, give a short plan (files to create or change) and wait for approval.
3. **Run what you build.** Run `pytest` after every change. Run the shell and try the new commands. Fix failures before reporting.
4. **Be honest.** Say clearly what was tested, what was partly tested, and what was not tested. Separate "really run on Windows" from "mocked".
5. **Keep it simple.** No extra abstraction layers. Small functions, type hints, short docstrings.
6. **No placeholders.** A command is either fully working with error handling, or it is not registered.
7. **Report format.** Report:
   - What was built or changed.
   - Tested vs untested (explicitly distinguish mocked vs really run on Windows).
   - Commands to try.

## New command checklist
When adding or updating a command:
1. **Register in registry**: Register the command in `core/registry.py` via `commands/` with metadata (name, description, category, usage, argument rules).
2. **Tab completion**: Add completion support in `core/completer.py`.
3. **Theme tokens only**: Use theme tokens from `core/theme.py`; never hardcode ANSI escape codes or hex colors.
4. **Escape user text**: Wrap all user-supplied text, arguments, and paths with `rich.markup.escape()`.
5. **CommandResult outcomes**: Handlers must report outcomes via `CommandResult` (`CommandResult.fail()` or `CommandResult.cancel()`, or `CommandResult.success()`).
6. **Plain mode ASCII**: Ensure output degrades to strict ASCII in plain mode (no emoji or fancy Unicode).
7. **Add tests**: Add unit and integration tests in `tests/` using `tmp_path` and mocks where appropriate.
8. **Regenerate documentation**: Run `python tools/gen_docs.py` to update `docs/commands.md`.

## Release checklist
When preparing a release:
1. Bump version in `core/version.py`.
2. Update `CHANGELOG.md` with release notes.
3. Regenerate documentation (`python tools/gen_docs.py`).
4. Run tests: `pytest`.
5. Run Windows build: `packaging\build_windows.bat`.
6. Verify executable flags: test `--version` and `--selftest`.
7. Check git status to ensure working tree is clean.
8. Commit, tag (e.g. `vX.Y.Z`), and push.
9. **Never commit `dist/` or `build/`**.

## Visual style
- Pastel palette (pink, lavender, mint) plus switchable themes (catppuccin, tokyo-night, rose-pine, gruvbox).
- Original animal mascots only: cat, bunny, bear, fox, penguin, shiba. Do not copy existing characters (Hello Kitty, anime characters, etc.).
- Mascot reacts: happy on success, worried on error, sleepy on exit.
- A plain-text fallback theme must always exist for old consoles.
- Look is a theme layer. It must never reduce functionality.

## Command Failure Reporting & Reactive Mascot Moods
Command handlers report execution outcomes uniformly by returning a `CommandResult` (`core/executor.py`):
- `CommandResult.success(message)`: Command succeeded normally. The executor sets the mascot mood to `happy`.
- `CommandResult.fail(message)`: Command encountered an error or refused an invalid action (e.g., flag argument, protected process, wildcard delete, bad alias, unknown command, missing folder). The executor sets the mascot mood to `worried`, marks the history entry as failed (`success=False`), and logs a warning with the command name only (no arguments or paths logged, preserving user privacy).
- `CommandResult.cancel()`: The user aborted an interactive prompt or confirmation (e.g. answering 'N' to a prompt). The executor sets the mascot mood to `neutral` (neither happy nor worried), does not log a warning, and does not treat cancellation as an error.
Handlers must use `CommandResult.fail()` / `CommandResult.cancel()` / `CommandResult.success()`.

## Repo Hygiene
- Never leave scratch scripts, test folders, exported files or logs inside the project folder. Use the system temp folder or an ignored `scratch/` folder, and delete them when finished.
- Tests must only use `tmp_path`, never create folders in the project.
- Before reporting a task or stage complete, run `git status` and list any untracked files that are not source, tests, docs or packaging files. Remove them or tell the user.
- Never commit build output (`build/`, `dist/`), `config.json`, `history.json`, logs or exported reports.



