# Changelog

All notable changes to MayuriShell are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
