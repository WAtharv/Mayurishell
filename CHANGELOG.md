# Changelog

All notable changes to MayuriShell are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Project-Aware Commands (`project info`, `project tree`, `project doctor`, `project env`):**
  - Non-destructive project root detection starting at current directory (never `os.getcwd`) and walking up at most 8 levels, stopping at drive root (`.git`, `pyproject.toml`, `requirements.txt`, `setup.py`, `setup.cfg`, `package.json`, `Pipfile`, `environment.yml`, `Dockerfile`, `manage.py`).
  - Project stack detection for `python`, `ml` (numpy, pandas, torch, tensorflow, scikit-learn), `flask`, `fastapi`, `node`, `docker` via file names and capped 256 KB read of manifests with `tomllib`. Never executes, imports, or installs from projects.
  - `project info`: High-level summary of name, root, detected stacks, git tracking, capped python files count, tests/readme presence, and declared dependency count (sanitized, lines containing `://` or `@` redacted).
  - `project tree [path] [--depth N] [--all]`: Directory hierarchy capped at depth (default 3), 300 entries, 3-second budget, directories first. Skips excluded folders (`.git`, `node_modules`, `venv`, etc.) unless `--all`. Detects symlinks and junctions via lstat and `FILE_ATTRIBUTE_REPARSE_POINT` without descending into them. Strictly refuses filesystem drive roots and home directory as tree root. Formats with themed Unicode or plain-mode ASCII branches.
  - `project env`: Virtual environment inspection for Python projects reading ONLY `pyvenv.cfg` (version, base home), showing PowerShell and cmd activation commands as text, checking real Python on PATH (reusing doctor service), reporting `.env` file presence without ever reading it or printing variable values, and listing requirements files.
  - `project doctor`: 10 non-destructive health checks (root found, python detected, venv exists, manifests, git tracking, tests folder, README, .gitignore, `.env` not ignored, venv not ignored) with plain-text fix commands.
- **Read-Only Git Assistant (`git status`, `git log`, `git diff`, `git branches`, `git summary`):**
  - Strict allowlist refusing all write subcommands (`commit`, `push`, `pull`, `add`, `reset`, `checkout`, `switch`, `restore`, `clean`, `stash`, `rebase`, `merge`, `rm`, `config`, `remote`, `tag`, etc.) with read-only notice.
  - Hardened execution through a single isolated runner: argument list, `shell=False`, stdin closed (`subprocess.DEVNULL`), 10-second timeout, 1MB output read cap, UTF-8 decode with `errors="replace"`, top-level hardening flags (`--no-pager`, `-c core.quotepath=false`, `-c core.fsmonitor=false`, `-c core.pager=cat`, `--no-optional-locks`), subcommand flags (`--no-ext-diff`, `--no-textconv`, `--no-color`, `--ignore-submodules=all`), isolated env (`GIT_TERMINAL_PROMPT=0`, `GIT_OPTIONAL_LOCKS=0`, `LC_ALL=C`), and all inherited `GIT_*` overrides stripped.
  - Strict path validation for diff: must resolve inside repository, must not start with `-`, passed after `"--"`.
  - Output sanitization: ANSI escape sequences and control characters stripped, credentials in URLs redacted (`***@`), status display capped at 50 files, diff capped at 200 lines.
  - Porcelain v2 status parser (branch, ahead/behind counts, staged, modified, untracked, conflicts).
  - Commit log with validated `-n 1..50` count (default 10, author name, no emails).
  - Branches showing local branches, active branch marked, upstream tracking info, no remote URLs.
  - Summary showing branch, working tree change counts, last commit (short hash, subject, relative date), and harmless read-only next suggestions.
  - Error classification explaining common issues with safe fix hints (not a git repo, safe.directory, no commits, detached HEAD, conflicts, index.lock, path not found, timeout).
  - Cheap prompt branch reader: non-blocking read of `.git/HEAD` (normal, worktree `gitdir:`, detached 7-char hash) walking up max 8 levels with directory caching, mtime invalidation, HTML escaping, control char stripping, 30-char cap, and NO subprocess invoked.
  - Shell prompt toggle (`prompt git on|off`) and config preference (`preferences.prompt_git`).
  - Added Git availability check in `doctor`.
  - Added `git` and `project` to `FORBIDDEN_COMMANDS` in workflow engine.
- **Tab Completion & Suggestions:**
  - Tab completion and typo suggestion support for `project`, `git`, and `prompt` subcommands and options; git write subcommands strictly excluded.
- **Self-Test Integration:**
  - Added `project info` against isolated temporary project in `--selftest`.

- **Config Management Subcommands (`config export`, `config import`, `config backup`, `config restore`):**
  - `config export [file]`: Exports whitelisted shell configuration (themes, mascots, safe preferences, shortcuts, workflows, organize categories, search directories) to a clean, sanitized JSON format (`schema_version: 1`). Sensitive data (history, logs, backups, undo journal, username, hostname, credentials) are strictly excluded. Automatically normalizes home paths to `~/`. Refuses overwriting existing files or following symlinks. Falls back gracefully to user home folder if Desktop is not writable, with user warning regarding personal folder/app paths.
  - `config import <file> [--dry-run] [--overwrite]`: Enforces 1MB size limit and schema version <= 1. Strictly refuses symlinks/junctions and non-regular files. Comprehensive diff preview table categorizing items into ADDED, UNCHANGED, CONFLICTING, and SKIPPED. Previews workflow steps with resolved targets (folder paths and final search URLs) and flags steps whose shortcuts do not exist on this PC. Full application shortcut targets listed with launch notices and separate confirmation prompt for executable shortcuts. Atomic apply to `config.json` via temporary file and flush before replacement, with automatic pre-import backup.
  - `config backup`: Generates timestamped snapshot in `backups/` using safe atomic writes. Never automatically deletes existing backups; warns when backup count exceeds 50.
  - `config restore [name]`: Lists available backups with timestamps and sizes when run without arguments. Restores configuration from plain filename resolving inside `backups/`. Rejects directory separators, path traversal, symlinks, and junctions. Validates backup structure (themes, mascots, apps, websites, folders, aliases, workflows) *before* touching current config; refuses corrupt files. Creates pre-restore backup first and applies atomically.
- **Doctor System Health Diagnostics (`doctor [apps|python|config|all]`):**
  - Comprehensive system health and troubleshooting inspection command with read-only invariant (never modifies configuration or executes automatic fixes).
  - `doctor apps`: Validates configured applications (existence on PATH or disk, batch script limitations), folder shortcuts (3-second timeout on disk/network path checks), website URL templates, and workflow step validity and target resolution.
  - `doctor python`: Checks Python installations on system PATH with 5-second timeout and closed streams (`stdin=DEVNULL`). Automatically detects Microsoft Store redirector stubs without executing them and warns users.
  - `doctor config`: Validates `config.json` and `history.json` integrity, performs ephemeral probe writes (`.probe_<uuid>.tmp`) to test write access on base data, logs, backups, and desktop directories inside `try/finally` blocks ensuring immediate deletion, and inspects backup counts.
  - Read-only Windows Registry protocol inspection (`HKCU\Software\Classes` and `HKEY_CLASSES_ROOT`) returning `UNKNOWN` on non-Windows/CI or registry errors, never writing.
  - Strict privacy protections: console report never prints environment variables, usernames, or hostnames, table detail column wraps with `overflow="fold"`, and logging records only summary event counts (`OK`, `WARN`, `FAIL`, `UNKNOWN`) without logging user paths or targets.
  - Added `doctor` to `--selftest` and command suggestions.
  - Added hint in `diagnostics` referencing `doctor`.
- **Shell Completion & Suggestions:**
  - Added tab completion in `core/completer.py` for `config` subcommands (`export`, `import`, `backup`, `restore`, options, backup names, file paths) and `doctor` categories (`apps`, `python`, `config`, `all`).
  - Added smart suggestion candidate rules for `config` and `doctor` subcommands in `core/suggestions.py`.

## [0.1.1] - 2026-10-22

### Fixed
- **Application Window Visibility:**
  - Removed `SW_HIDE` from `launch_detached()` in `services/application_discovery.py` so GUI applications (`notepad`, `calculator`, `code`, etc.) display their normal interactive windows instead of running invisibly in the background.

### Added
- **Smart Command Suggestions:**
  - Logic-only suggestions engine (`core/suggestions.py`) providing ranked typo corrections for commands, subcommands, options, and shortcuts using prefix matching and `difflib` (cutoff 0.6, < 50ms execution).
  - Contextual hints on unknown commands: history frequency suggestions, directory path hints (capped at 200 entries, non-recursive, no file reading), and installed application discovery hints with session `shutil.which` caching.
  - Interactive next-prompt prefill: automatically prefills the top suggestion on the very next interactive prompt when confident, and clears immediately on run, cancel (Ctrl+C), or input change.
  - Safe failure hints across 8 command failure scenarios via `CommandResult.fail(..., hint=...)` (unknown commands, missing directories, missing applications, flag arguments refused on shortcuts, non-templated website shortcuts, protected system processes, invalid shortcut/alias names, and wildcard delete refusals).
  - `suggestions` command (`suggestions [on|off]`) with tab completion, allowing users to toggle smart suggestions or inspect status.
  - Safe alias collision protection ensuring `suggestions` cannot be shadowed by user-defined aliases.

### Changed
- **Privacy & Secret Protection:**
  - Truncated echoed unknown command names to 40 characters.
  - Added secret and token detection: inputs matching secret filters or long token-like strings suppress all suggestions, print clean "Command not found.", and are purged from history.
  - Destructive command guard: if the closest match is a destructive command (`delete`, `move`, `rename`, `copy`, `process`, `organize`, `workflow`, `alias`, `config`), only the command name and its usage line are shown, never typed arguments or prompt prefill.
  - Unknown command failure logging records only event counts (`Command failed: unknown command (count: N)`), never user input or arguments.

## [0.1.0] - 2026-10-20

### Initial Release: Personal Productivity Shell for Windows

#### Added
- **Core Engine & Architecture:**
  - Robust command parser supporting single quotes, double quotes, and Windows paths with backslashes.
  - Safe extensible command registry with argument validation and fuzzy command suggestions.
  - Command executor with uniform `CommandResult` outcome reporting (`success`, `fail`, `cancel`).
  - Per-user configuration manager (`%APPDATA%\MayuriShell\`) with atomic writes, automatic pre-save backup rotation, and corrupted file auto-recovery.
  - Persisted command history with secret sanitization and history management commands (`history`, `history clear`).
  - Rotating error logging (`logs/mayurishell.log`) with strict user privacy preservation (command names logged only, never paths or arguments).

- **Visual Style & Animal Mascots:**
  - Pastel color themes: `kawaii`, `catppuccin`, `tokyo-night`, `rose-pine`, `gruvbox`, and `plain`.
  - 6 original animal companions: `cat`, `bunny`, `bear`, `fox`, `penguin`, and `shiba`.
  - Reactive mascot expressions that respond dynamically to command success (`happy`), error or refusal (`worried`), and exit (`sleepy`).
  - Fetch-style system startup screen and `fetch` command displaying companion art alongside real-time hardware telemetry.
  - Plain-text ASCII fallback mode automatically activated on older consoles lacking UTF-8 or truecolor support.

- **Launchers & Shortcuts:**
  - Application launcher supporting PATH discovery, Start Menu shortcuts, and URI schemes (`spotify:`, `discord:`, `whatsapp:`).
  - Executable shortcut arguments (e.g. `code .`, `code projects\my-app`) resolving paths against working directory and refusing flag injections.
  - Website shortcut engine supporting query templates (e.g. `youtube`, `google`, `github` searches) with control character stripping and URL validation.
  - Configurable folder shortcuts (`desktop`, `downloads`, `documents`, `projects`, `home`) and shortcut management (`add-folder`, `remove-folder`, `folders`).
  - User-defined aliases with loop and conflict detection (`alias`, `unalias`, `aliases`).

- **File Management & Search:**
  - Built-in navigation: `pwd`, `ls` (with `-a` and `-l`), `cd`, `open`.
  - Safe file operations: `mkdir`, `touch`, `copy`, `move`, `rename`, and `delete`.
  - Multi-tier deletion safeguards: deletion requires confirmation (`y/N`), refuses wildcards, requires `-r` for folders, and protects drive roots, home directories, Windows folders, Program Files, installation directories, and `%APPDATA%`.
  - Fast recursive file search (`find`) with wildcard patterns, exclusion lists, and timeout cancellation.

- **System Telemetry & Process Inspection:**
  - Real-time hardware monitors: `sysinfo`, `cpu`, `memory`, `disk`, `uptime`.
  - Process management: `processes` with sorting/limiting, `process find`, and detailed `process inspect`.
  - Guarded process termination (`process kill`) preventing accidental kills of critical Windows system services (System, csrss, wininit, lsass, explorer, etc.).

- **Productivity & Automation:**
  - Safe file organization (`organize`): categorizes top-level files by extension, presents an interactive move plan, supports dry runs (`--dry-run`), avoids touching subfolders or recent downloads, and renames conflicting destinations safely.
  - Granular undo journal (`organize undo`): writes moves after each file to allow full reversal even if interrupted mid-run.
  - Project scaffolding (`create-project`): generates starters for `python`, `ml`, `datascience`, `flask`, and `fastapi`, as well as user-defined custom templates.
  - Workflows system (`workflow`): chains registered actions into reusable multi-step automation without arbitrary code execution.
  - System diagnostics (`diagnostics`): inspects terminal capabilities and allows sanitized diagnostic exports to Desktop (`diagnostics --export`).

- **Packaging & Build System:**
  - Standalone Windows 64-bit PyInstaller build with console support and hidden import hooks.
  - Automated repeatable build batch scripts (`build_windows.bat` and `build_installer.bat`).
  - Non-interactive CLI switches: `--version`, `--selftest`, and `--config-dir`.
  - Inno Setup 6 installer (`installer.iss`) supporting per-user install, Start menu shortcuts, Windows Terminal integration, and uninstaller configuration preservation.
  - SHA256 checksum generation for release archives.
