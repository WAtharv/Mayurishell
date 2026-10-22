# RULES.md - MayuriShell (always apply)

## Safety (non-negotiable)
- Never use `shell=True` with user input. Use `subprocess` with argument lists.
- Never execute arbitrary Python (`eval`, `exec`) or run unknown commands as Windows commands. Unknown input gets "command not found" plus suggestions.
- Only commands in the registry can run. Workflows may only call registered actions.
- Never load or run code from plugins or workflow files.
- Confirm before: delete, process kill, bulk moves, overwriting anything.
- Never overwrite silently. If a target exists, ask or pick a safe new name.
- Bulk file operations (`organize`, bulk move) must support dry run and show the plan before acting.
- Never delete files automatically. `organize` only moves.
- Never kill critical system processes (System, csrss, wininit, winlogon, services, lsass, smss, explorer by default). Keep a protected-process list.
- Do not request admin rights. Do not change Windows system settings.
- Do not install packages or touch global environments (`create-project` only creates files).
- Suggestions and hints are text only. They never auto-execute. Only registered commands can be suggested or prefilled, and never destructive ones.
- App shortcut arguments must be existing resolved paths. No flags, and never pass arguments to .cmd or .bat files.
- Anything that waits for input must not wait in --version, --selftest, piped or non-interactive runs.
- Always give any command that might wait for input a timeout.

## Git and workspace safety
- Never run git checkout, git reset, git clean, or delete or overwrite any file you did not create in this task, without asking me first. Say what you want to discard and why.

## Config, logs and data
- Per-user data lives in `%APPDATA%\MayuriShell\` (`config.json`, `history.json`, `logs/`, `backups/`). Never inside the install or project folder.
- Create defaults on first run. Validate config on load.
- If config is malformed: back it up, report it, fall back to defaults. Do not crash.
- Back up config before destructive changes.
- Expand `%ENVVARS%` and `~` in paths.
- Never hardcode personal paths or assume an app is installed.
- Never log or store passwords, tokens or API keys. Skip history entries that look like secrets (`password`, `token`, `secret`, `api_key`).
- Never log typed commands, arguments, search queries or paths. Log only names and results.
- Logs rotate (max about 1 MB x 3 files).

## Code quality
- Python 3.11+, type hints, `pathlib` for all paths, `shlex` for parsing (quotes and Windows paths must work).
- Every command defines: name, description, handler, usage, category, argument rules.
- `core/` never imports from `commands/`.
- A failing command must never crash the shell. Catch errors in the executor, log them, show a friendly message.
- Keep functions small. No unneeded abstractions or dependencies.
- Use Rich for all output. Use consistent formatting across commands.
- Nothing may depend on `__file__`, the project folder or the working directory, because the app also runs as a frozen PyInstaller exe. Use `core/paths.py`.

## Testing
- Use `pytest` with temporary directories (`tmp_path`). Mock `subprocess`, `os.startfile` and `webbrowser`.
- Never touch real user files in tests.
- Required tests: parser (quotes), registry, aliases (conflicts and loops), config validation, history, file operations, organize preview, workflow validation.
- Run `pytest` after every change and fix failures before reporting.

## Honesty
- State clearly what was tested, partly tested or untested.
- When reporting, separate "really run on Windows" from "mocked".
- Do not claim a Windows-only feature works unless it was run on Windows.
- Do not claim the installer or `.exe` was built or tested unless it was.
- If a feature is too big, ship a smaller complete version. Never ship a stub as complete.

## Look and feel
- Themes live in `core/theme.py` and config. Colors and mascots are never hardcoded inside commands.
- Original mascots only. No copyrighted characters.
- Always keep a plain fallback theme (no emoji, no fancy Unicode).
- All output uses theme tokens and escaped user text, and works in plain mode as strict ASCII. The prompt never contains emoji.
- Detect terminal capability. Degrade gracefully if truecolor or Unicode is missing.

## Process
- One stage or feature at a time. Plan, wait for approval, build, test, summarize.
- Do not modify files outside the scope of the current task.
- Ask before adding any new dependency.
- Keep end-of-stage and feature summaries short.
