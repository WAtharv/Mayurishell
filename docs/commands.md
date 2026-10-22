# MayuriShell Command Catalog (v0.1.1)

This document lists every command available in MayuriShell. It is automatically generated from the internal command registry metadata.

## Table of Contents

- [Aliases](#aliases)
- [Appearance](#appearance)
- [Applications](#applications)
- [Builtins](#builtins)
- [Customization](#customization)
- [Files](#files)
- [Folders](#folders)
- [General](#general)
- [Launchers](#launchers)
- [Navigation](#navigation)
- [Organization](#organization)
- [Processes](#processes)
- [Productivity](#productivity)
- [Search](#search)
- [System](#system)
- [Websites](#websites)
- [Workflows](#workflows)

---

## Aliases

### `dl`

**Description:** Alias for: downloads

**Usage:** `dl [args...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > dl
```

### `gh`

**Description:** Alias for: github

**Usage:** `gh [args...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > gh
```

### `yt`

**Description:** Alias for: youtube

**Usage:** `yt [args...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > yt
```

---

## Appearance

### `fetch`

**Description:** Display system fetch dashboard with mascot art and hardware info

**Usage:** `fetch`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > fetch
```

### `mascot`

**Description:** Inspect and select your original animal mascot companion

**Usage:** `mascot [name|random]`

**Arguments:** Minimum: `0`, Maximum: `1`

**Examples:**
```text
mayuri@pc > mascot
mayuri@pc > mascot bunny
mayuri@pc > mascot fox
mayuri@pc > mascot shiba
```

### `pet`

**Description:** Pet your mascot companion and watch them react

**Usage:** `pet`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > pet
```

### `theme`

**Description:** Inspect, preview, and switch visual color themes

**Usage:** `theme [name|preview]`

**Arguments:** Minimum: `0`, Maximum: `1`

**Examples:**
```text
mayuri@pc > theme
mayuri@pc > theme kawaii
mayuri@pc > theme catppuccin
mayuri@pc > theme tokyo-night
mayuri@pc > theme preview
```

---

## Applications

### `calculator`

**Description:** Launch application: calculator

**Usage:** `calculator [paths...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > calculator
```

### `code`

**Description:** Launch application: code

**Usage:** `code [paths...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > code
```

### `discord`

**Description:** Launch application: discord

**Usage:** `discord [paths...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > discord
```

### `notepad`

**Description:** Launch application: notepad

**Usage:** `notepad [paths...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > notepad
```

### `spotify`

**Description:** Launch application: spotify

**Usage:** `spotify [paths...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > spotify
```

### `whatsapp`

**Description:** Launch application: whatsapp

**Usage:** `whatsapp [paths...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > whatsapp
```

---

## Builtins

### `clear`

**Description:** Clear the terminal screen

**Usage:** `clear`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > clear
```

### `diagnostics`

**Description:** Display environment diagnostics or export a sanitized report

**Usage:** `diagnostics [--export]`

**Arguments:** Minimum: `0`, Maximum: `1`

**Examples:**
```text
mayuri@pc > diagnostics
mayuri@pc > diagnostics --export
```

### `exit`

**Description:** Exit MayuriShell gracefully

**Usage:** `exit`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > exit
```

### `help`

**Description:** Display command list or details for a specific command

**Usage:** `help [command]`

**Arguments:** Minimum: `0`, Maximum: `1`

**Examples:**
```text
mayuri@pc > help
mayuri@pc > help organize
mayuri@pc > help cd
```

### `history`

**Description:** Display command history or clear stored history

**Usage:** `history [clear]`

**Arguments:** Minimum: `0`, Maximum: `1`

**Examples:**
```text
mayuri@pc > history
mayuri@pc > history clear
```

### `version`

**Description:** Display MayuriShell and runtime version information

**Usage:** `version`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > version
```

---

## Customization

### `add-app`

**Description:** Add or update an application shortcut

**Usage:** `add-app <name> <path_or_command>`

**Arguments:** Minimum: `2`, Maximum: `2`

**Examples:**
```text
mayuri@pc > add-app vlc 'C:\Program Files\VideoLAN\VLC\vlc.exe'
```

### `add-folder`

**Description:** Add or update a folder shortcut that opens in File Explorer

**Usage:** `add-folder <name> <path>`

**Arguments:** Minimum: `2`, Maximum: `2`

**Examples:**
```text
mayuri@pc > add-folder notes ~/Notes
mayuri@pc > add-folder work 'D:\Work'
```

### `add-website`

**Description:** Add or update a website shortcut

**Usage:** `add-website <name> <url>`

**Arguments:** Minimum: `2`, Maximum: `2`

**Examples:**
```text
mayuri@pc > add-website docs https://docs.python.org
mayuri@pc > add-website yt https://youtube.com/results?search_query={query}
```

### `alias`

**Description:** Create an alias or list aliases

**Usage:** `alias [name] [command...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > alias
mayuri@pc > alias gs 'git status'
mayuri@pc > alias c clear
```

### `aliases`

**Description:** List all configured command aliases

**Usage:** `aliases`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > aliases
```

### `suggestions`

**Description:** Toggle or inspect smart command suggestions (on|off)

**Usage:** `suggestions [on|off]`

**Arguments:** Minimum: `0`, Maximum: `1`

**Examples:**
```text
mayuri@pc > suggestions
```

### `unalias`

**Description:** Remove an alias

**Usage:** `unalias <name>`

**Arguments:** Minimum: `1`, Maximum: `1`

**Examples:**
```text
mayuri@pc > unalias gs
mayuri@pc > unalias c
```

---

## Files

### `copy`

**Description:** Copy a file or directory with overwrite protection

**Usage:** `copy [-y] <source> <destination>`

**Arguments:** Minimum: `2`, Maximum: `3`

**Examples:**
```text
mayuri@pc > copy file.txt backup.txt
mayuri@pc > copy notes.txt projects\
```

### `delete`

**Description:** Safely delete file or directory to Recycle Bin

**Usage:** `delete [-r] [-y] <target>`

**Arguments:** Minimum: `1`, Maximum: `3`

**Examples:**
```text
mayuri@pc > delete old_file.txt
mayuri@pc > delete -r temp_directory
```

### `info`

**Description:** Display detailed metadata about a file or folder

**Usage:** `info <path>`

**Arguments:** Minimum: `1`, Maximum: `1`

**Examples:**
```text
mayuri@pc > info
```

### `mkdir`

**Description:** Create a new directory

**Usage:** `mkdir <folder>`

**Arguments:** Minimum: `1`, Maximum: `1`

**Examples:**
```text
mayuri@pc > mkdir new_folder
mayuri@pc > mkdir "my project"
```

### `move`

**Description:** Move a file or directory with overwrite protection

**Usage:** `move [-y] <source> <destination>`

**Arguments:** Minimum: `2`, Maximum: `3`

**Examples:**
```text
mayuri@pc > move draft.txt archive\
mayuri@pc > move test.txt ..\
```

### `open`

**Description:** Open a file with its default application

**Usage:** `open <file>`

**Arguments:** Minimum: `1`, Maximum: `1`

**Examples:**
```text
mayuri@pc > open report.pdf
mayuri@pc > open "my notes.txt"
```

### `rename`

**Description:** Rename a file or folder in place (plain name only)

**Usage:** `rename [-y] <target> <new_name>`

**Arguments:** Minimum: `2`, Maximum: `3`

**Examples:**
```text
mayuri@pc > rename old.txt new.txt
mayuri@pc > rename "draft v1.txt" "draft v2.txt"
```

### `touch`

**Description:** Create a new empty file or update timestamp

**Usage:** `touch <file>`

**Arguments:** Minimum: `1`, Maximum: `1`

**Examples:**
```text
mayuri@pc > touch notes.txt
mayuri@pc > touch newfile.py
```

---

## Folders

### `desktop`

**Description:** Open folder in File Explorer: ~/Desktop

**Usage:** `desktop`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > desktop
```

### `documents`

**Description:** Open folder in File Explorer: ~/Documents

**Usage:** `documents`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > documents
```

### `downloads`

**Description:** Open folder in File Explorer: ~/Downloads

**Usage:** `downloads`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > downloads
```

### `home`

**Description:** Open folder in File Explorer: ~

**Usage:** `home`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > home
```

### `projects`

**Description:** Open folder in File Explorer: ~/Projects

**Usage:** `projects`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > projects
```

---

## General

### `command-info`

**Description:** Display detailed information about a command or shortcut

**Usage:** `command-info <name>`

**Arguments:** Minimum: `1`, Maximum: `1`

**Examples:**
```text
mayuri@pc > command-info
```

### `commands`

**Description:** List all registered commands and shortcuts

**Usage:** `commands`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > commands
```

### `config`

**Description:** Display configuration file locations

**Usage:** `config`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > config
mayuri@pc > config show
mayuri@pc > config get username
mayuri@pc > config set prompt_symbol $
mayuri@pc > config reset
mayuri@pc > config path
mayuri@pc > config backup
mayuri@pc > config restore
```

---

## Launchers

### `apps`

**Description:** List configured applications and their status

**Usage:** `apps`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > apps
```

### `websites`

**Description:** List configured website shortcuts

**Usage:** `websites`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > websites
```

---

## Navigation

### `cd`

**Description:** Change working directory (supports ~, .., drive letters, and shortcuts)

**Usage:** `cd [path|shortcut]`

**Arguments:** Minimum: `0`, Maximum: `1`

**Examples:**
```text
mayuri@pc > cd projects
mayuri@pc > cd ..
mayuri@pc > cd ~
mayuri@pc > cd downloads
```

### `ls`

**Description:** List directory contents with size, date, and extension filter

**Usage:** `ls [-a] [path] [pattern]`

**Arguments:** Minimum: `0`, Maximum: `3`

**Examples:**
```text
mayuri@pc > ls
mayuri@pc > ls -a
mayuri@pc > ls -l
mayuri@pc > ls projects
mayuri@pc > ls -a -l downloads
```

### `pwd`

**Description:** Print current working directory

**Usage:** `pwd`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > pwd
```

---

## Organization

### `organize`

**Description:** Analyze directory and organize files into categorized folders

**Usage:** `organize <folder or shortcut> [--dry-run] [--include-other] | organize undo`

**Arguments:** Minimum: `1`, Maximum: `3`

**Examples:**
```text
mayuri@pc > organize downloads
mayuri@pc > organize downloads --dry-run
mayuri@pc > organize downloads --include-other
mayuri@pc > organize undo
```

---

## Processes

### `process`

**Description:** Process management tools (find, info, kill, list)

**Usage:** `process <find|info|kill|list> [arguments]`

**Arguments:** Minimum: `0`, Maximum: `5`

**Examples:**
```text
mayuri@pc > process find python
mayuri@pc > process inspect 1234
mayuri@pc > process kill 5678
```

### `processes`

**Description:** List running processes with CPU and Working Set memory usage

**Usage:** `processes [--sort cpu|memory|name] [--limit N]`

**Arguments:** Minimum: `0`, Maximum: `4`

**Examples:**
```text
mayuri@pc > processes
mayuri@pc > processes --sort mem
mayuri@pc > processes --limit 15
```

---

## Productivity

### `create-project`

**Description:** Create a project directory from a configurable starter template

**Usage:** `create-project <name> [--template <t>] [--here]`

**Arguments:** Minimum: `1`, Maximum: `5`

**Examples:**
```text
mayuri@pc > create-project my-app
mayuri@pc > create-project ml-pipeline --template ml
mayuri@pc > create-project api-server --template fastapi
mayuri@pc > create-project --list-templates
```

### `templates`

**Description:** List available built-in and custom project scaffolding templates

**Usage:** `templates`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > templates
```

---

## Search

### `find`

**Description:** Search for files in configured directories

**Usage:** `find <query> [--ext <extension>] [--limit <number>]`

**Arguments:** Minimum: `1`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > find report.pdf
mayuri@pc > find *.py
mayuri@pc > find "machine learning"
```

---

## System

### `cpu`

**Description:** Display detailed CPU utilization and core statistics

**Usage:** `cpu`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > cpu
```

### `disk`

**Description:** Display storage drive usage and capacity in GB

**Usage:** `disk`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > disk
```

### `memory`

**Description:** Display RAM and swap file statistics

**Usage:** `memory`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > memory
```

### `sysinfo`

**Description:** Display comprehensive system overview summary

**Usage:** `sysinfo`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > sysinfo
```

### `uptime`

**Description:** Display system boot timestamp and uptime

**Usage:** `uptime`

**Arguments:** Minimum: `0`, Maximum: `0`

**Examples:**
```text
mayuri@pc > uptime
```

---

## Websites

### `chatgpt`

**Description:** Open website: https://chatgpt.com

**Usage:** `chatgpt`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > chatgpt
```

### `github`

**Description:** Open website: https://github.com/search?q={query}

**Usage:** `github [query...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > github
```

### `google`

**Description:** Open website: https://www.google.com/search?q={query}

**Usage:** `google [query...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > google
```

### `youtube`

**Description:** Open website: https://www.youtube.com/results?search_query={query}

**Usage:** `youtube [query...]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > youtube
```

---

## Workflows

### `workflow`

**Description:** Manage and execute multi-step automation workflows

**Usage:** `workflow [list | show <name> | run <name> [--dry-run] | add <name> <steps...> | remove <name> | validate]`

**Arguments:** Minimum: `0`, Maximum: `Unlimited`

**Examples:**
```text
mayuri@pc > workflow list
mayuri@pc > workflow run dev
mayuri@pc > workflow show web
mayuri@pc > workflow add study 'notion, spotify'
mayuri@pc > workflow remove study
```

---
