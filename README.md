# herdr-routines

Cron for commands inside [Herdr](https://herdr.dev). A routine is a
scheduled command; running an agent is just a command in a pane
(`claude "Review my PRs."`), which Herdr natively detects and tracks.

See `SPEC.md` for the full behavior spec and `examples/routines.toml` for a
starting config.

## Install

```sh
herdr plugin link /path/to/herdr-routines
herdr plugin config-dir herdr-routines   # put routines.toml there
herdr plugin action invoke herdr-routines.validate
herdr plugin action invoke herdr-routines.start
```

## Config

`routines.toml` in the plugin config dir:

```toml
[settings]
shell = "fish"
workspace = "routines"

[[routine]]
name = "morning-repo-review"
cron = "0 9 * * mon-fri"
cwd = "~/Workspace/Repos/homelab-k3s"
command = 'claude "Review open PRs and summarize what needs my attention."'
notify = true
```

The daemon reloads the file automatically when it changes; invalid edits
keep the previous config loaded.

## Actions

| action | what it does |
|---|---|
| `herdr-routines.start` | start the scheduler daemon (detached, pidfile in state dir) |
| `herdr-routines.stop` | stop the daemon |
| `herdr-routines.status` | daemon state, per-routine last fire + last error |
| `herdr-routines.validate` | check routines.toml |
| `herdr-routines.list` | list configured routines |

Run a routine immediately (actions can't take arguments):

```sh
python3 /path/to/herdr-routines/src/main.py run morning-repo-review
```

## Fish wrapper (optional)

```fish
function herdr-routines
    python3 /path/to/herdr-routines/src/main.py $argv
end
funcsave herdr-routines
```

Then: `herdr-routines list`, `herdr-routines run morning-repo-review`.

Per-routine keybinding in Herdr's `config.toml`:

```toml
[[keys.command]]
key = "ctrl+r"
type = "shell"
command = "python3 /path/to/herdr-routines/src/main.py run morning-repo-review"
description = "run morning review now"
```

## Notes

- Schedules match local wall-clock time; standard cron DST quirks apply
  (a routine inside the skipped hour won't fire that night unless
  `catch_up = true`; the repeated hour may fire twice).
- Missed runs are skipped while the machine sleeps; opt into one late
  catch-up run with `catch_up = true`.
- State and logs live in the plugin state dir: `daemon.log`, `runs.jsonl`,
  `state.json`, `daemon.pid`.
