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

## Actions

`start` · `stop` · `status` · `validate` · `list` — via
`herdr plugin action invoke herdr-routines.<action>`.

Run a routine now: `python3 src/main.py run <name>`.

## Development

```sh
herdr plugin link .
python3 -m unittest discover -s tests
```
