# T05 / T10 / T03b 的 R040g 前置绑定

当前入口为 R045 v17、R044 v7、R047 v12。它们读取 R040f 的真实 `failed_harness` 封存，并要求 R040g 为 `measured`，且 `base.commit` 和 `experimental.candidate_commit` 均为 `effb9969706922ddad9e59b96377e46469ebe97f`。历史 T20 的 0aa 身份单列保留。

复用既有 `require_closed_round` 与 canonical history checker，没有新增封存检查框架。R040f 已归档其只读 `round_json_append.py`，三入口实际消费均通过。各入口的新 FILEdry/review 路径隔离旧签名；未改变候选、工作负载、性能判据或 shutdown 行为。

冻结源为 `/data2/FreeToken/runs/dev_shutdown_fixes/tail_r040g_bindings_cpu_v2/source`，共55个文件。Linux选择的六组入口、前置、POSIX闭合和T03b收尾回归共 **143项通过，4.30秒**；此前 Windows 为128通过、15个POSIX项跳过。原收尾修复的82项证据继续按未变源保留，不重复算成新增行为覆盖。

v1的三个失败是fixture修改了未被消费者读取的capsule checker；v2将其指向实际round-local checker，并在临时目录构造symlink后恢复只读权限。失败stage和日志保留，运行源码未为此修改。

| 证据 | SHA-256 |
|---|---|
| source_manifest.sha256 | `3774e7a0f38514d2013ab80821c8e085225e09952b19d16df993794a3ffaeb2d` |
| pytest.log | `0461a5ec9ae048a011a951f2a3737721d6fcb4cb856bfad2e0a4101b243d18a8` |
| R045入口 | `9be56f33b1a41e662717336aade730ae91af25faea1792b3e324e89a5d36640b` |
| R044入口 | `05e85ca53a06c7ff8ba345859a442b82f3cea86c521396114bfefead23f998d8` |
| R047入口 | `07e18eaff166685cc6499769f3f68f7d1a7cef2820bca2d81572d01fdd1da3ef` |
| 独立源码复核 | `3634f94a9415c1fb95111c441d812e7b82df60a14e94c03f2ea3ff6428947a95` |

独立复核原件：`/data2/FreeToken/runs/dev_shutdown_fixes/reviews/tail_r040g_bindings_source_review_v2.json`。本地报告见 `TAIL_R040G_BINDINGS_CPU_REPORT_20261008.json`、`TAIL_R040G_BINDINGS_SOURCE_REVIEW_20261008.json`。

这些证据只证明CPU/source及前置消费边界。R040g尚未完成，三个入口均不能进行正式FILEdry或GPU启动；须等各自真实前置后再执行同入口空跑与独立启动复核。
