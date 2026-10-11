# T17 D14 exact-ID GPU gate

R022 / batch50 passed independent review and was sealed. R023 / batch51 stopped at the first measured cold-versus-hit output/state mismatch and was independently sealed `not_met`. All 76 original raw files remain unchanged. [Measured result](../plan/01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md), [closure receipt](t17_r023_close_receipt.json), [next diagnostic](t17_r023_computation_diagnosis.md).

The candidate is `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42`, directly based on E2-base `23f2e2caa3395837c9474735ffc83321f3b9b5a1`.

## Frozen evidence

- CPU stage: `/data2/FreeToken/runs/dev_D14/t17_08cd1c8ca06f/cpu_validation.json`; SHA256 `530a49543c54c4a3b4e1abd130dcc33f150a98765c5d942d892a81d305cbaae8`.
- Actual Linux: helper 14 PASS, GPU-contract 10 PASS, artifact 3 PASS; uint8 signed-zero negative control PASS. Normal multiprocessing spawn preserves input IDs and installs restore, input, token-reply and layer-child observers. CUDA remains uninitialized in these CPU checks.
- Fourteen source/input files are frozen in the receipt. The actual execution copy is `/tmp/ft-t17-d14-gerhsbyr/`; its runner SHA256 is `24928eae2ac36e79157db0a18b5f25086d576f5bda267462c2f7ff79b6d96070`.
- Batch PID/PGID: 300919; observed start_ticks: 121959591. [Launch receipt](t17_d14_E2-R023-gate-T17_launch_receipt.json).
- R022 prerequisite: round SHA `976ac037e235dbb230dd9dcdee4a0ef3ea7dbe77c8e98e117ec339f0104f9d1f`; review SHA `87bf64185a6897493a20a0ab92905494a4e626cb0ee876ca7c36e173105ad2bb`.

## Measured protocol

For boundaries 8192, 12416, 18944 and 12736, construct a donor of L+1 exact token IDs from the real historical frontend trace. Generate two tokens with ignore_eos enabled, preserving the nonterminal donation. Extend the identical prefix with declared synthetic suffixes: short query L+65, long query L+4161. Generate exactly 128 tokens at temperature zero for each query. Each cold comparison uses a separate fresh service process. Prefix IDs are copied; suffix construction is explicitly recorded in real_inputs.json.

The private test endpoint sends T17ExactIdsMsg through the actual tokenizer queue. The worker produces an int32 UserMsg without decode/re-encode. Retain the raw HTTP body, UID, input hash and sampling receipt. Observers record actual admission, executed prefill, DetokenizeMsg.next_token, terminal reason and layer-child initial-state flags.

Joint resume-device dumps contain the actual source and destination slots. All four roles (GDN conv, GDN recurrent, PLE conv and PLE ngram) require matching shape/dtype and uint8 bytes. Restore-copy comparisons and cold-versus-hit computed-state comparisons remain separate. Acceptance also requires identical actual sampled token IDs and complete text. Any mismatch retains the original artifacts and stops acceptance.

## Tools

- t17_d14_stage.py: exclusive remote CPU stage and frozen source/input receipt.
- t17_d14_launch.py / t17_d14_start.py: sealed R022 checks, resource preflight, immutable execution copy, atomic round/batch reservation and owned-process launch.
- t17_d14_gpu.py: actual donor/hit/cold services and evidence comparisons.
- t17_d14_observe.py / t17_d14_artifacts.py: observational wrappers and raw-evidence validation.
- t17_owned_launch_protocol.py: byte-identical 7e1c05a reviewed reservation/owned-stop functions; its historical main is not an operator entry point.
- t17_d14_monitor.py: read-only exact receipt, frozen SHA, process group/session/start-time and status inspection.

```powershell
python development/t17_d14_monitor.py
```

Read-only helper modes remain available: --cpu-replay, --inspect-known-dump and --preflight-gpu. They establish their own bounded evidence only. E2-base.1 and corrected T10 remain downstream of accepted T17 evidence. R023 is a retained measured counterexample; matched-block diagnostic preparation does not change its verdict.
