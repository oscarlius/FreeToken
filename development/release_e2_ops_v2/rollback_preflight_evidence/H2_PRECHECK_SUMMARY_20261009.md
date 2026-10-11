# H2 rollback preflight — terminal read-only blocker

Scope: `/data2/FreeToken/src/FreeToken` rollback identity
`184c965964b5f79deaecf1b1e3e0eda3187c829d`; owned archive directory
`/data2/FreeToken/runs/dev_release/rollback_preflight_20261009_1340_v1`.

The worktree HEAD matched the requested commit and `ft serve --help` returned
zero. The command ran from the owned CPU archive directory with
`PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=/data2/FreeToken/src/FreeToken/python`, and
`CUDA_VISIBLE_DEVICES=''`. It did not start a service, call an endpoint, or
acquire a GPU.

The required status condition did not pass: both exact commands
`git status --porcelain --untracked-files=all --ignored` were nonempty. The
raw output is retained in `git_status_before.stdout.txt` and
`git_status_after.stdout.txt`, each SHA-256
`d77de81764e0beb687bdbf60cde8206661faecfe169094c85228136e102b7844`.
Their first entries are ignored `.pytest_cache/*`,
`python/freetoken.egg-info/*`, and `python/**/__pycache__/*`; no cleanup was
attempted. This is the terminal H2 preflight blocker.

`ft serve --help` output SHA-256 is
`3dd0564cae93c85ae54b17ba0d3fc485895093dba44cff3ca726e0ace7efc6a7`.
The check is split correctly in `preflight_supplement.json`: 19 `ft serve`
options are present in that help output and the 2 launcher options are present
in `numactl --help`; neither group has an unsupported option. The first receipt
records the raw first classification; the supplement preserves it and corrects
the launcher-versus-`ft` ownership boundary without rerunning `ft`.

For historical evidence, `serve_final_8192.log` was read only and has full-file
SHA-256 `6bba876c6ecd21906e9478ea820c0aecdbc3a5a8cf3c9715c473c32d1fe1b65b`.
The first receipt's literal `cached_rows` word search is superseded by
`H2_DEEP_CHECK_SUMMARY_20261009.md`: the real R066 `cached_rows()` regex finds
68 prefill triples. The log still has no API `usage` dictionary with
prompt/completion/total fields, and no exact req-SDK-report filename exists in
the historical directory; it cannot support an SDK usage claim.

Remote primary receipt SHA-256:
`04180a98135b991459d8b8773086f2d480ed0ad67f14f7e50b1fdfa8fe061313`.
Remote bounded supplement SHA-256:
`055908f0ff51754cf42524dca22deaf874f2ce500f71e79c4e825b81f762bb4e`.
