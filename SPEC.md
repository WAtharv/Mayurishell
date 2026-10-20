# MAYURISHELL
## A Customizable Command Environment and Personal Productivity Tool for Windows

### 1. Project Vision

MayuriShell is a fully functional Windows application: a customizable command environment that lets users interact with their computers through their own commands, shortcuts and workflows.

It is a personal shell where users can launch applications, manage files, navigate directories, inspect system information, search for files, create aliases, automate repetitive tasks, and eventually interact with their computers using natural language.

Examples:

```text
mayuri@pc > spotify            Launches Spotify.
mayuri@pc > projects           Opens the configured projects directory.
mayuri@pc > find report.pdf    Searches configured directories for the file.
mayuri@pc > sysinfo            Displays system information.
mayuri@pc > organize downloads Analyzes Downloads and offers to organize files by category.
mayuri@pc > create-project my-ai-app   Creates a project directory from a configurable template.
```

The application should be modular, extensible, configurable, and suitable for distribution to other Windows users.

**This is not a tutorial exercise or a throwaway prototype. It must be a usable application with multiple integrated functionalities, proper error handling, configuration management, testing, documentation, and a distributable Windows build.**

Do not stop after implementing a few example commands.

---

# 2. Primary Requirements

Build MayuriShell with these priorities:

1. Functional command execution.
2. Multiple useful built-in commands.
3. A customizable command and alias system.
4. Reliable Windows integration.
5. File and directory management.
6. System monitoring and application launching.
7. Custom workflows and automation.
8. Per-user configuration.
9. Extensible architecture.
10. Standalone Windows distribution.
11. Testing, documentation, and error handling.
12. A clear upgrade path for AI capabilities.

Implement these as an integrated application rather than disconnected demonstrations. Use reasonable engineering judgment for small implementation details.

---

# 3. Technology Stack

- **Python:** Core command engine.
- **Rich:** Terminal interface and formatted output.
- **prompt_toolkit:** Input, history navigation and tab completion.
- **psutil:** System and process information.
- **pathlib:** File and directory operations.
- **subprocess:** Application launching.
- **JSON:** Configuration and user-defined aliases.
- **SQLite:** Optional, only if it provides a clear benefit.
- **pytest:** Automated testing.
- **PyInstaller:** Standalone executable packaging.
- **Inno Setup:** Windows installer (optional for personal use).

Prefer the Python standard library when practical. Avoid unnecessary dependencies, servers, databases or cloud services. Core functionality must work locally without an internet connection.

---

# 4. Feature Set

## Feature 1: Interactive Command Environment

A polished terminal interface with:

- Custom startup screen.
- Personalized prompt.
- Command input and command history.
- Clear-screen functionality.
- Command descriptions.
- Helpful error messages.
- Argument parsing, including quoted paths and filenames.
- Unknown-command handling.
- Graceful exit.
- Keyboard-friendly interaction.
- Consistent output formatting.

Example:

```text
╔══════════════════════════════════════════════╗
║                 MAYURISHELL                  ║
║          YOUR PC. YOUR COMMANDS.             ║
╚══════════════════════════════════════════════╝

Welcome back, Mayuri!

Type 'help' to explore your commands.

mayuri@pc >
```

The interface should be polished but must not sacrifice functionality for visual effects.

## Feature 2: Application Launcher

Users launch installed applications using short commands: `spotify`, `code`, `notepad`, `calculator`, `discord`.

Implement:

- Application aliases.
- Configurable executable paths.
- PATH-based application discovery.
- Common Windows application discovery strategies.
- URI-based launching when supported.
- Application-not-found handling.
- Listing of configured applications.
- Easy registration of new application shortcuts.

Do not assume an application is installed on every computer. Do not hardcode personal application paths.

## Feature 3: Website Launcher

Commands for opening websites: `youtube`, `github`, `google`, `chatgpt`.

Support:

- Configurable website aliases.
- Opening URLs in the default browser.
- Adding new website shortcuts.
- Listing configured websites.
- Validating URLs.
- Useful error messages.

Users can create their own website commands through configuration or a built-in command.

## Feature 4: File and Directory Navigation

Commands: `desktop`, `downloads`, `documents`, `projects`, `home`.

Functionality:

- Open directories in File Explorer.
- Navigate within the shell's own directory context.
- Display the current directory.
- List directory contents.
- Open files with their default applications.
- Create directories and files.
- Copy, move and rename files.
- Delete files with appropriate confirmation.
- Search for files.
- Filter by extension.
- Display file information.

Example syntax:

```text
pwd
ls
cd projects
open "D:\Study Notes\report.pdf"
mkdir my-project
touch notes.txt
copy notes.txt backup.txt
move notes.txt archive\
rename old.txt new.txt
```

Support sensible Windows-compatible syntax. The shell's own directory navigation is separate from the working directory of any external Windows terminal. Never overwrite or delete important files silently.

## Feature 5: Advanced File Search

A file-search system that searches user-configured directories.

```text
find report.pdf
find *.py
find "machine learning"
```

Support:

- Partial filename matching.
- Extension filtering.
- Recursive search.
- Search-directory configuration.
- Permission-error handling.
- Exclusion of configurable directories.
- Search cancellation where practical.
- Clear result formatting.

Do not recursively scan the entire computer by default.

## Feature 6: System Information

`sysinfo` displays:

- Operating system and Windows version where available.
- Python runtime version.
- CPU usage and core information.
- RAM usage and available memory.
- Disk usage.
- Current user and hostname.
- System uptime where available.

Specialized commands: `cpu`, `memory`, `disk`, `uptime`. Handle unavailable metrics gracefully.

## Feature 7: Process Management

```text
processes
process find chrome
process find python
```

Provide:

- Process listing and name filtering.
- PID display.
- Basic CPU and memory information.
- Process inspection.
- Optional process termination.

Termination must require confirmation. Never terminate critical system processes. Do not attempt to bypass Windows security restrictions.

## Feature 8: Custom Command Registry

A command registry that allows new commands to be added without rewriting the shell engine.

Every registered command defines:

- Command name.
- Description.
- Handler.
- Argument requirements.
- Usage information.
- Optional category.
- Appropriate error handling.

Support: `help`, `commands`, `command-info spotify`, `history`, `clear`, `exit`.

Unknown commands produce useful suggestions when possible.

## Feature 9: Aliases and Personal Commands

```text
alias yt youtube
alias gh github
alias dl downloads
```

Provide commands for:

- Creating, listing and removing aliases.
- Persisting aliases across restarts.
- Detecting alias conflicts.
- Preventing recursive alias loops.
- Displaying alias descriptions.

Users must not need to edit Python source code to customize ordinary shortcuts.

## Feature 10: Configuration Management

Store configuration under:

```text
%APPDATA%\MayuriShell\
├── config.json
├── history.json
├── logs/
└── backups/
```

Support:

- Username or prompt customization.
- Application paths, website shortcuts, folder shortcuts.
- User-defined aliases.
- Search directories and excluded directories.
- Display preferences and theme.
- Command behavior preferences.

Requirements:

- Create defaults on first launch.
- Validate configuration values.
- Recover gracefully from malformed configuration.
- Back up configuration before potentially destructive changes.
- Preserve configuration across application upgrades.
- Expand Windows environment variables and user-directory paths.
- Provide a command to display configuration locations.
- Never place personal configuration inside the application's installation directory.

## Feature 11: File Organization

```text
organize downloads
```

The shell should:

1. Inspect the configured directory.
2. Identify files by extension and category.
3. Generate a proposed organization plan.
4. Display the planned moves.
5. Ask for confirmation.
6. Move files into appropriate folders.
7. Avoid overwriting existing files.
8. Report successes and failures.

Support a dry-run mode. Never automatically delete files.

## Feature 12: Project Scaffolding

```text
create-project my-ai-app
```

Allow users to select or configure templates: Python project, machine learning project, data science project, Flask application, FastAPI application.

Example Python project:

```text
my-ai-app/
├── src/
├── tests/
├── README.md
├── requirements.txt
├── .gitignore
└── pyproject.toml
```

Generate sensible starter files. Do not install packages, create cloud resources, or modify global environments without explicit user consent.

## Feature 13: Command History

```text
history
history clear
```

- Persist history across sessions.
- Display recent commands and allow inspection.
- Support basic filtering.
- Handle corrupted history safely.
- Provide a way to clear history.
- Avoid storing passwords, API keys or other secrets.

## Feature 14: Multi-Step Workflows

A safe workflow system that combines registered actions.

Example development workflow:

1. Open a configured project directory.
2. Launch VS Code.
3. Open the project's terminal or development environment.
4. Optionally run a predefined startup command.

Another workflow might open a collection of frequently used websites.

- Workflow definitions use registered actions, not unrestricted arbitrary code.
- Require confirmation for destructive or consequential operations.
- Workflows are configurable and reusable.

## Feature 15: Logging and Diagnostics

- Application error logging.
- Command execution diagnostics.
- Clear error messages.
- Log rotation or a reasonable size limit.
- A diagnostics command.
- A way to locate log files.
- Protection against recording sensitive information unnecessarily.

The application must not crash because a single command fails.

---

# 5. Command Design

Provide a consistent command syntax.

**Applications and websites:** `spotify`, `code`, `youtube`, `github`, `apps`, `websites`

**Files and directories:** `pwd`, `ls`, `cd`, `open`, `mkdir`, `touch`, `copy`, `move`, `rename`, `delete`, `find`, `desktop`, `downloads`, `documents`, `projects`

**System and processes:** `sysinfo`, `cpu`, `memory`, `disk`, `uptime`, `processes`, `process find <name>`

**Configuration and customization:** `help`, `commands`, `alias`, `aliases`, `add-website`, `add-folder`, `config`

**Productivity:** `organize downloads`, `create-project my-ai-app`, `history`, `workflow`

**Shell management:** `clear`, `version`, `diagnostics`, `exit`

Treat these as a target command catalog, not permission to implement incomplete placeholder handlers. Every documented command must have real functionality and sensible error handling. If a feature is too large, implement a smaller complete version instead of an unfinished stub.

---

# 6. Architecture

```text
MayuriShell/
├── main.py
├── requirements.txt
├── pyproject.toml
├── README.md
├── .gitignore
├── config/default_config.json
├── core/
│   ├── shell.py  parser.py  registry.py  executor.py
│   ├── config_manager.py  history.py  aliases.py
│   └── logging_config.py  exceptions.py  theme.py
├── commands/
│   ├── applications.py  websites.py  navigation.py  files.py
│   ├── search.py  system.py  processes.py  customization.py
│   ├── organization.py  project_scaffolding.py
│   └── workflows.py  builtins.py  appearance.py
├── services/
│   ├── application_discovery.py  file_service.py
│   └── system_service.py  workflow_service.py
├── tests/
│   ├── test_parser.py  test_registry.py  test_aliases.py
│   └── test_config.py  test_files.py  test_workflows.py
├── packaging/
│   ├── build_windows.bat  mayurishell.spec  installer.iss
└── docs/
    ├── commands.md  configuration.md  packaging.md
```

The structure may be adjusted, but the core engine must stay independent of individual command implementations. Avoid excessive abstraction layers.

---

# 7. Safety Requirements

MayuriShell interacts with the user's computer. Security and reliability are essential.

- Do not use `shell=True` with untrusted user input.
- Do not execute arbitrary Python expressions.
- Do not automatically run unknown commands as Windows commands.
- Validate paths and arguments.
- Prevent accidental file overwrites.
- Require confirmation before destructive operations.
- Support dry runs for bulk file operations.
- Do not terminate critical system processes.
- Avoid administrator privileges unless necessary.
- Do not modify Windows system settings without explicit authorization.
- Keep configuration and logs separate from application binaries.
- Do not expose secrets in logs or command history.
- Do not execute arbitrary code loaded from plugins or workflow files.

Use an allowlisted command registry and explicit execution policies.

---

# 8. Distribution Requirements

The application must be distributable to other Windows users.

- Use PyInstaller to bundle the Python runtime and dependencies.
- Use Inno Setup to create a Windows installer.
- The release includes: a standalone executable, a repeatable installer build process, Start menu shortcuts, an optional desktop shortcut, normal uninstall support, per-user configuration initialization, and documentation for installation and troubleshooting.

Users must not need Python or a development environment. The application must not depend on the author's personal directory structure or installed applications.

Do not claim an installer has been tested unless it has actually been built and tested. If time is short, finish the application first and provide a working, documented packaging process.

---

# 9. Testing Requirements

Automated tests for:

- Command parsing and quoted arguments.
- Command registration.
- Alias resolution and alias loops.
- Configuration validation.
- History persistence.
- Invalid commands.
- File operations.
- File-organization previews.
- Workflow validation.

Use temporary directories and mocked external processes. Do not perform destructive tests on real user files. Run the test suite and fix failures. Perform integration tests for Windows-specific behavior where the environment permits. Clearly distinguish between tested, partially tested, and untested features.

---

# 10. Future AI Integration

Keep the architecture ready for a future AI command assistant. In a later version, users might type natural-language requests such as:

```text
mayuri@pc > open my python project and start vs code
mayuri@pc > find the pdf I downloaded yesterday
```

An AI layer would translate such requests into calls to **registered commands only**, show the plan to the user, and require confirmation before running anything consequential. It must never execute arbitrary code or shell commands.

For now, do NOT build the AI feature. Only keep the design ready:

- Commands expose structured metadata (name, description, usage, arguments) that an AI layer can read.
- All command execution goes through one executor, so an AI layer can call the same entry point as a human.
- The AI layer would be optional and off by default, and the app must work fully without it or an internet connection.

---

# 11. Visual Theme

MayuriShell has a kawaii, Linux-"rice" style look.

- Fetch-style startup screen: mascot art on the left, system info on the right (user@host, Windows version, uptime, shell version, CPU, RAM, disk, theme, number of commands and aliases). A `fetch` command shows it any time.
- Pastel default palette (pink, lavender, mint) with rounded boxes.
- Switchable themes via a `theme` command: kawaii, catppuccin, tokyo-night, rose-pine, gruvbox, plain.
- Original animal mascots only (cat, bunny, bear, fox, penguin, shiba). Do not copy existing characters or brands.
- The mascot reacts: happy on success, worried on error, sleepy on exit.
- A plain-text fallback theme must exist for old consoles (no emoji or fancy Unicode).
- Theme is stored in config. The look must never reduce functionality.
