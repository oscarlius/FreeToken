# R040a private-port owner handoff

## 当前 2026-10-07 11:27：第十二节配置迁移

第十二节新增当前入口 `r040a_d16_supplement_prepare_v4.py`，dry `r040a_d16_dryrun_v3.py`、私有owner_v2、anchor_v3；两类服务都使用98304/.88。旧v3/owner_v1/anchor_v2冻结保持，shutdown v3/collector v2不改。启动review新目录r040a_startup_review_v5、dry schema v4；默认及实际after-round为E2-R048，R046b依赖名已更正。新 v4 Linux CPU v2 已对 entry/owner/anchor/collector 四个运行组件 175 PASS（pointer `R040A_SECTION12_LINUX_CPU_20261007_v2.json`，CVD 空、guard 生效、torch 未加载）。v1 临时目录失败已核实为测试把 `os.getuid()` mock 为321后触发 pytest owner 检查，不是 `/tmp` 属主错误；真实路径空跑及 R 签字仍待完成，不能复用旧176或旧签字。


`r040a_private_port_owner_v1.py` exposes `make_owner(gpu_module, native_run,
lifecycle, options, ...)` and `install(owner, gpu_module=..., lifecycle=...,
file_dry_run=...)`. Pass the retained actual GPU module, its native `Run`, and
D07's reviewed `stop_owned_process` lifecycle. The owner publishes one dynamic
endpoint as `owner.port` and `owner.base_url`; collectors must receive it.

Formal and file-only calls use the same `owner.service` through source
admission, compiled-extension binding, environment snapshot, command receipt,
and `serve.log` creation. File-only returns immediately before `Popen`; it has
no synthetic argv and performs no readiness, requests, service startup, or
cleanup. Formal mode uses the private URL for health/readiness, retains parser
and strict-argument checks, and delegates process-group cleanup to D07.

The helper never probes, binds, requests, or otherwise refers to the shared
service port. Its CPU test compares all pre-Popen formal files with the
file-only path using a `Popen` sentinel, and verifies lifecycle stop handoff.
## 根集成：10-07 第十节 Linux CPU 与来源复核

最终执行入口为 `/data2/FreeToken/runs/dev_D16/r040a_section10_cpu_v1/development/r040a_d16_supplement_prepare_v3.py`，工作树是 clean 发布树 `/data2/FreeToken/wt/e2base1-ordinary-rewind`、`0aa23431e5b800797543bdecbf35a01045131d7d`。Linux 集成 176/176 PASS：`r040a_section10_cpu_v1/report.json` SHA `a01c60ea2d0d89800ce42fe37c06ed34426472ab631ee3b173f4a1ef7af3c1be`，源码 MANIFEST SHA `47ec23b87d12764083537591ecc556da0e25be1d99287314487c69cc47189b45`。

独立 R 的 collector 来源准入回执为 `/data2/FreeToken/runs/dev_D16/r040a_section10_collector_source_review_v1/review.json`，SHA `f014c517617127618ee683a9c62626505e84b369e0ce5b314adc47acf3014f5b`，文件444/目录555。现有 collector v2 的 `verify_source_review` 实调用 PASS，17真实角色与103 CPU文件绑定，shutdown v3 原字节不改。实际 native Run 构造 `proc=None`、CUDA 未初始化；这仅证明 CPU 来源准入，不是 GPU 启动复核。

当前 R046a/batch80 OOM 后队列停止。R040a 按第十节排在 R048 之后；不能把 R051 kept 替换为队列前置以提前启动。以下真实路径空跑命令只登记，须在用户解除队列阻塞且 R048 实际 measured+D04 后执行。不要运行开发目录下的旧入口，否则 owner/source/path 绑定不同。

```bash
cd /data2/FreeToken
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/data2/FreeToken/runs/dev_D16/r040a_section10_cpu_v1/development/cpu_guard:/data2/FreeToken/runs/dev_D16/r040a_section10_cpu_v1/development \
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/dev_D16/r040a_section10_cpu_v1/development/r040a_d16_supplement_prepare_v3.py \
  --dry-run --after-round E2-R048 \
  --dry-run-dir /data2/_shared/runs/ft_rounds/.dryrun_R040a_section10_v1 \
  --collector-review /data2/FreeToken/runs/dev_D16/r040a_section10_collector_source_review_v1/review.json \
  --collector-review-sha256 f014c517617127618ee683a9c62626505e84b369e0ce5b314adc47acf3014f5b \
  --anchor-seed-sha256 499c39e4e601d8c61e8305265569c5055083eb14e5da9940b10c656f5e9c97e9
```

剩余：同入口实际文件空跑 → R 的真实 dry/前置/source 启动签字 → 依队列 GPU 测量 → 独立原始复算 → D04。本轮未启动模型、取锁、分批或创建正式 R040a 目录。


## v6 source-capsule closure

`r040a_d16_supplement_prepare_v6.py::required_capsule_files()` is the sealed-package
inventory used before CPU dry-run or launch.  It includes the T17 owner import chain,
all eight immutable helper archive entries, the retained D16 collector dependencies,
and `equiv_suite` capture/reader modules.  `equiv_suite` sources must be copied from
the pinned D16 CPU source package and bound in the new `MANIFEST.sha256`; a collector
summary cannot substitute for them.

## Sealed v6 capsule pointer

The reviewed CPU-only v6 source capsule is at
`/data2/FreeToken/runs/dev_D16/r040a_v6_source_capsule_20261007_165310/source_tools`.
Its `MANIFEST.sha256` is
`239765e183f35ed611789b3c19501054443986db0586887ea9034f3cfc8b1bce`.
`reports/cpu_receipt.json` (`75125dfb87a8a4f26b19c1845b57a34d3e6ee22a7943fccd5b5ca408196d3456`)
and `reports/metadata_preflight.log` (`88b05d4887e57a182253bf2067dd9beef894d686b6aed4dfac49d06a33d49904`)
record the CVD-hidden source build, actual private-owner file writer, and
metadata-only predecessor check.  This is not a launch approval.  The present
canonical R040a CPU review pin has `source_execution_ready=false`, so the
same-entry dry-run remains intentionally unstarted until a new sealed source
review binds this v6 manifest and collector review.

## 2026-10-07 — v6 collector-compatible CPU evidence

`/data2/FreeToken/runs/dev_D16/r040a_v6_cpu_report_20261007_170940_v6/reports/cpu_report.json` is a CPU-only report (`ft_d16_exact_startup_cpu/v1`, `PASS`) with 17 role-specific, relative, read-only inventory entries. It records 89 targeted tests under `CUDA_VISIBLE_DEVICES=''` and the socket guard, an actual sealed `create_service_owner(..., file_dry_run=True)` writer run, and direct `_cpu_moe` / `_pinned_tensor` imports with CUDA uninitialized. It is not a startup review and cannot authorize GPU execution. The later `ft_d16_collector_source_review/v1` must bind its `source_files` directly to `reports/source_files_template.json` and the exact report SHA.
