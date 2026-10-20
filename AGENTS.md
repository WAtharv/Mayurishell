# AGENTS.md - MayuriShell

## What this project is
MayuriShell is a customizable command shell for Windows, written in Python. Users type short commands (`spotify`, `projects`, `organize downloads`) to launch apps, open sites and folders, manage files, inspect the system and run workflows. It has a kawaii / Linux-rice visual theme (pastel colors, original animal mascots, fetch-style startup screen).

The full spec is in `SPEC.md`. Re-read it at the start of every stage. Hard rules are in `RULES.md` and always apply.

## Tech stack
- Python 3.11+
- rich (output), prompt_toolkit (input, history, tab completion), psutil (system info)
- pathlib, shlex, subprocess, json, logging (standard library)
- pytest (tests)
- PyInstaller (packaging, last stage only)

No other dependencies unless asked first.

## Project structure
```
MayuriShell/
  main.py
  requirements.txt
  README.md
  SPEC.md  AGENTS.md  RULES.md
  core/        shell, parser, registry, executor, config_manager,
               history, aliases, logging_config, exceptions, theme
  commands/    applications, websites, navigation, files, search,
               system, processes, customization, organization,
               project_scaffolding, workflows, builtins, appearance
  services/    application_discovery, file_service,
               system_service, workflow_service
  tests/
  packaging/
  docs/
```
`core/` must never import from `commands/`. Commands register themselves with the registry.

## How to work
1. **Work one stage at a time.** Only build the stage the user names. Do not touch other stages.
2. **Plan first.** Before writing code, give a short plan (files to create or change) and wait for approval.
3. **Run what you build.** Run `pytest` after every change. Run the shell and try the new commands. Fix failures before reporting.
4. **Be honest.** Say clearly what was tested, what was partly tested and what was not tested. Never claim a Windows feature works unless it was run on Windows.
5. **Keep it simple.** No extra abstraction layers. Small functions, type hints, short docstrings.
6. **No placeholders.** A command is either fully working with error handling, or it is not registered.
7. **Summarize briefly** at the end of each stage: what was built, how to try it, what is left.

## Stages
1. Core: config manager, parser, registry, shell loop, `help`, `clear`, `exit`, `history`, `version`
2. Launchers: apps, websites, folder shortcuts, aliases, `add-website`, `add-folder`, `apps`, `websites`
3. Files and search: `pwd`, `ls`, `cd`, `open`, `mkdir`, `touch`, `copy`, `move`, `rename`, `delete`, `find`
4. System and processes: `sysinfo`, `cpu`, `memory`, `disk`, `uptime`, `processes`, `process find`, guarded kill
5. Look: themes, original animal mascots, reactive mascot face, `fetch` startup screen, themed prompt
6. Productivity: `organize` (dry run first), `create-project`, workflows, `diagnostics`
7. Packaging: PyInstaller build script, README, install and troubleshooting docs

## Definition of done (every stage)
- All commands in the stage work and handle bad input with a clear message.
- Tests exist and pass.
- Nothing crashes the shell; errors are logged and shown nicely.
- User confirmed it works on their own Windows PC.

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
- Before reporting a stage complete, run `git status` and list any untracked files that are not source, tests, docs or packaging files. Remove them or tell the user.
- Never commit build output (`build/`, `dist/`), `config.json`, `history.json`, logs or exported reports.


