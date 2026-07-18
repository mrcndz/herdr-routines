# herdr-routines

Cron for your agents inside [Herdr](https://herdr.dev). A routine is a
scheduled command — running an agent is just `claude "your prompt"` in a
pane, natively detected and tracked by Herdr.

## Install

```sh
herdr plugin install mrcndz/herdr-routines
herdr plugin config-dir herdr-routines   # put routines.toml there
herdr plugin action invoke herdr-routines.start
```

## Configure

```toml
# routines.toml
[[routine]]
name = "morning-repo-review"
cron = "0 9 * * mon-fri"
cwd = "~/Workspace/Repos/my-project"
command = 'claude "Review open PRs and summarize what needs my attention."'
notify = true
```

Schedules are `cron = "M H DOM MON DOW"` or `every = "30m"`. The daemon
picks up config changes automatically. See `SPEC.md` for the full
behavior spec.

## Options

### `[settings]` — file-wide defaults

| key | default | description |
|---|---|---|
| `shell` | `$SHELL`, else `sh` | shell that runs command strings, pre and post hooks |
| `workspace` | `"routines"` | default workspace label for pane routines |
| `max_log_lines` | `1000` | max lines kept in the `runs.jsonl` run log |

### `[[routine]]` — one block per routine

Required: `name`, one schedule (`cron` or `every`), and one action
(`command` or `action`).

| key | default | description |
|---|---|---|
| `name` | — | unique routine name; also the tab label |
| `description` | — | optional free text, shown by `list` |
| `cron` | — | 5-field cron: `*`, lists `1,3,5`, ranges `9-18`, steps `*/15`, names `mon-fri`, `jan` |
| `every` | — | interval sugar: `45s`, `15m`, `2h`, `1d`; exclusive with `cron` |
| `type` | inferred | `pane` (command in a tab), `shell` (daemon-side, no tab), `plugin_action`; inferred from `command`/`action` |
| `command` | — | shell string, run exactly as typed; or argv array for no-shell execution |
| `action` | — | plugin action id to invoke (`type = "plugin_action"`) |
| `cwd` | `~` | working directory for the command / tab |
| `shell` | from `[settings]` | per-routine shell override |
| `enabled` | `true` | `false` parks the routine without deleting it |
| `workspace` | from `[settings]` | workspace label (pane routines only) |
| `workspace_id` | — | target an exact workspace id; implies `require`; exclusive with `workspace` |
| `workspace_mode` | `"reuse"` | `reuse` (find or create), `create` (new one per firing), `require` (fail if missing) |
| `tab_mode` | `"reuse"` | `reuse` (one tab per routine) or `create` (new tab per firing) |
| `focus` | `false` | `true` jumps to the tab when the routine fires |
| `close_when_done` | `false` | appends `; exit` so the pane closes itself when the command finishes |
| `pre` | — | daemon-side hook before everything; non-zero exit skips the firing |
| `post` | — | daemon-side hook after the command exits; `shell`/`plugin_action` types only |
| `notify` | `false` | Herdr notification when the routine fires, is skipped, or fails |
| `catch_up` | `false` | if scheduled times were missed (daemon down, laptop asleep), fire once, late |

Notes: missed runs are skipped by default (no anacron); cron matches local
wall-clock time; `pane` routines can't take `post` (chain
`command && post` instead) or be watched — fire-and-forget by design.

## Examples

An agent that triages your inbox every 15 minutes during work hours:

```toml
[[routine]]
name = "inbox-triage"
cron = "*/15 9-18 * * mon-fri"
command = 'claude "Check my inbox and flag anything urgent."'
```

A background command with no tab at all, plus a notification when done:

```toml
[[routine]]
name = "backup"
type = "shell"
cron = "0 3 * * *"
command = "restic backup ~/Documents"
post = "herdr notification show 'backup done' --sound done"
```

A cleanup whose tab closes itself when the command finishes:

```toml
[[routine]]
name = "nightly-cleanup"
cron = "30 22 * * *"
workspace = "maintenance"
command = "docker system prune -f"
close_when_done = true
```

A guarded routine — `pre` runs daemon-side and a non-zero exit skips the
firing (no workspace, no tab):

```toml
[[routine]]
name = "test-on-changes"
every = "30m"
cwd = "~/Workspace/Repos/my-project"
pre = "test -n \"$(git status --porcelain)\""   # only if there are changes
command = "just test"
```

A daily agent that missed schedules while your laptop slept still runs
once, late:

```toml
[[routine]]
name = "daily-briefing"
cron = "0 8 * * *"
catch_up = true
command = 'claude "Prepare my morning briefing from calendar and inbox."'
```

Another plugin's action on a schedule:

```toml
[[routine]]
name = "apply-layout"
cron = "0 9 * * mon-fri"
action = "example.layout.apply"
```

## Actions

Everything is exposed as plugin actions, invocable from the CLI or
bindable to keys:

```sh
herdr plugin action invoke herdr-routines.<action>
```

| action | what it does |
|---|---|
| `start` | start the scheduler daemon (detached; idempotent — safe to call again). Also fired automatically on `workspace.focused`, so the daemon comes up on its own once you focus any workspace |
| `stop` | stop the daemon (SIGTERM via pidfile) |
| `status` | daemon state, and per routine: schedule, last fire, disabled flag, last failure reason |
| `validate` | check `routines.toml`; prints every error with the routine name, or `0 errors, N routine(s) loaded` |
| `list` | one line per routine: name, type, schedule, description |

Example session:

```sh
$ herdr plugin action invoke herdr-routines.validate
0 errors, 3 routine(s) loaded

$ herdr plugin action invoke herdr-routines.status
daemon: running (pid 30370)
  morning-repo-review      [0 9 * * mon-fri]  last: 2026-07-18T09:00:00
  inbox-triage             [*/15 9-18 * * mon-fri]  last: 2026-07-18T17:45:00
  backup                   [0 3 * * *]  last: never  (disabled)
```

### Running a routine on demand

Herdr actions can't take arguments, so `run <name>` goes through the
script directly:

```sh
python3 <plugin-root>/src/main.py run morning-repo-review
```

Bind it to a key in Herdr's `config.toml`:

```toml
[[keys.command]]
key = "ctrl+r"
type = "shell"
command = "python3 <plugin-root>/src/main.py run morning-repo-review"
description = "run morning review now"
```

Or wrap it as a fish command:

```fish
function herdr-routines
    python3 <plugin-root>/src/main.py $argv
end
funcsave herdr-routines
```

Then: `herdr-routines run morning-repo-review`, `herdr-routines status`.

State and logs live in the plugin state dir
(`~/.local/state/herdr/plugins/herdr-routines/`): `daemon.log`,
`runs.jsonl` (one JSON line per firing), `state.json`, `daemon.pid`.

## Development

```sh
herdr plugin link .
python3 -m unittest discover -s tests
```
