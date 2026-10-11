# R067当前终态（2026-10-09）

R067/b132与第1次工装重试R067a/b133均failed_harness，累计2服务/1次HTTP请求尝试、0有效生成、0可比较格；旧T17 exact-ID工装不兼容481异步new_user，公开token-ID入口亦不支持。在不改代码约束下停止，保留≤64待证与原论文C3；两轮D04封存、GPU/自有锁已释放。

[实测报告](../../plan/01_测试与调研/results/T20-E2-R067_20261009.md)。本目录旧实验runner/hook仅为历史准备件，实际b132/b133使用归档的直接工具命令及既有T17组件，没有执行这些新runner/hook。

以下为历史准备说明。

# R067 D20 short-tail matrix preparation

RID `E2-R067-d20-short-tail` freezes D20 at
`d50be0f8f84ab1105f788be8f1354773ad539b63` against release/e2 base
`481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`.  This directory is CPU-only
preparation: it has no service-launch path and cannot acquire a GPU lock.

The requested plan is exactly six services and 26 generation calls: two hot
release/e2 services (one seed plus four tails for each prefix) and four cold
D20 services (A/B for each prefix). Prefixes are 8192/8256; tails are
1/30/63/64. Sampling is copied from the T17 exact-ID wrapper:
`max_tokens=128`, `temperature=0`, `top_p=1`, `ignore_eos=True`.

`r067_prepare.py --filedry <directory>` produces a source freeze and a
non-launching packet. The D20 `FT_DEV_PREFILL_SCHEDULE` flag is one-shot, so
`r067_cold_hook.py` provides a cold-only rearm point before the original
`Scheduler._process_one_msg`. It accepts only a specially marked request after
the scheduler is drained, verifies the message UID and actual int32 input SHA,
then restores a parsed schedule whose source SHA was frozen in the service
manifest. If the launcher supplies the first schedule through the environment,
the hook verifies it is in the manifest and clears it after stock initialization;
every query, including the first, enters through the same UID/SHA-bound rearm.
Ordinary requests remain on the original path. Cold services must use
`--cache-type naive`; the original schedule admission still rejects any cache hit.

Any future admission implementation must also reject
`/data2/FreeToken/run/production.cleanup_failed.json`, use the shared GPU
lock and dynamic ports, and reject ports 8095/8096. No GPU proof or service
start is represented by this packet.

CPU evidence is mirrored in `evidence_cpu_20261009/`. The remote FT-venv
probe proves that the special API-side message becomes `R067UserMsg` in a
spawned child, carries its UID/schedule/input SHA marker, and that the real
`Scheduler._process_one_msg` has the rearm wrapper installed. The message
types live in `r067_wire.py` at module scope; the probe exercises actual
`BaseTokenizerMsg` JSON encode/decode across parent/spawn and returns the
backend message across a multiprocessing queue. The accompanying CPU test
covers four sequential re-arms, a non-idle rejection, and terminal token-ID
receipt recording only for a verified cold UID.
The plan remains six services and 26 calls: two hot services use raw
release/e2 `481...` with one seed plus four queries each (10 calls), while
four D20 cold A/B services have four queries each (16 calls). No spare calls
are planned; 26 is within the 28-call limit.
