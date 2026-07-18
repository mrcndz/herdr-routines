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
picks up config changes automatically. See `SPEC.md` for all options
(workspace/tab behavior, pre/post hooks, catch-up, types).

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

`start` · `stop` · `status` · `validate` · `list` — via
`herdr plugin action invoke herdr-routines.<action>`.

Run a routine now: `python3 src/main.py run <name>`.

## Development

```sh
herdr plugin link .
python3 -m unittest discover -s tests
```
