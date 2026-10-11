# P1 保留快照证据核验器

`p1_snapshot_evidence.py` 是 `p1_snapshot_prepare.py` 的后续只读 CPU 工具。前者只检验声明字典；本工具的
`p1_snapshot_evidence_files/v1` 包要求一个显式 `--evidence-root`，并实际打开其中声明的文件：

- 每个路径必须相对该根目录、是普通文件，且路径自身和任一父路径都不能是符号链接；逃逸、缺失或链接一律拒绝。
- 对 accepted E2-base.1 收据、默认 T16 `kept` 收据、token IDs/trace/tokenizer，以及每个 process 的
  serve/startup/runner/compiled-extension 原文件逐字节 SHA-256 复算。
- accepted 收据必须在原始 JSON 中给出同一完整 commit、同一 code version 和 `verdict: accepted`；T16
  原始 JSON 必须给出该 commit 与 `verdict: kept`。
- 三个 retained process JSON 必须实际包含并逐字段等于声明的 `decode_snapshot`、`donation`、`restore`、
  `admission`、`consumer` 和 source binding；核验器随后从原始 record 重算 UID/slot/device-token 链约束。

这需要未来启动器保留上述**规范化 JSON record**及其文件 SHA；现有 `p1_snapshot_evidence/v1` 只含 hash 字符串，
没有文件路径、原始 receipt 内容或 process event record，不能由本工具回溯验证。本 v1 files packet 是对此缺口的
有界扩展，而非对历史 T03/E2-R008 的重写：其六份 `snapshot_count.json` 仍全为零，不能作为正例输入。

运行：

```powershell
python development/p1_snapshot_evidence.py --packet <packet.json> --evidence-root <retained-dir>
python -m pytest -q -p no:cacheprovider development/tests/test_p1_snapshot_evidence.py
```

通过仅证明该 packet 引用的当前保留字节和规范化记录彼此一致。它不验证这些 JSON 是否由真实服务进程写出，不能证明
进程出生、GPU decode donation 或 accepted E2-base.1 的运行时真实性，也不构成 P1 接受；这些仍须由未来冻结启动、
原始服务日志、实际 admission/restore 事件和独立复核完成。

## Linux CPU receipt

Linux CPU-only verification ran on SSH alias 9 with `/data2/FreeToken/venv/bin/python` and
`CUDA_VISIBLE_DEVICES=` / `PYTHONDONTWRITEBYTECODE=1`. The create-exclusive frozen stage is
`/data2/FreeToken/runs/p1_prepare/b3c9f053ea66`; after the run it has no writable files. It retained
only the four frozen source/test files, stdout/stderr logs, and `sha256sums.txt`.

`pytest -q -p no:cacheprovider development/tests/test_p1_snapshot_prepare.py development/tests/test_p1_snapshot_evidence.py`
returned `19 passed in 0.05s`; the Linux symlink negative control passed rather than being skipped. Exact source/log
SHA-256 values and the immutable stage manifest hash are in
`development/p1_snapshot_evidence_cpu_receipt.json` (stdout `2b147b57fc934f6eb2d26838c619470a18fafc9561e08f69a4eacfe079575e08`,
stderr empty SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).

This is a CPU test receipt only. It does not supply a real P1 positive-chain packet or establish GPU execution,
process birth, decode donation, accepted baseline runtime provenance, or P1 acceptance.
