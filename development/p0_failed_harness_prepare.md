# Failed-harness closure preparation (proposal only)

This is a read-only inventory. It does not mutate a server round, manufacture a `serve:none` declaration, or issue a D04 append.

Canonical root: `/data2/_shared/runs/ft_rounds`. Reviewed local D04 writer prerequisite: `67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff`; observed writer input: `a4bd8b095bf718076f4d4b7f9ed8d6f5a96263b80e455ae2324d4f3c67601c91` (match: `False`).

| round | D04 root files missing | service arms found | batch logs | closure proposal |
|---|---|---:|---:|---|
| E2-R001 | round.json, round_history, MANIFEST.sha256 | 1 | 1 | proposal_only: missing canonical D04 first-snapshot inputs |
| E2-R004 | round.json, round_history, MANIFEST.sha256 | 1 | 0 | proposal_only: missing canonical D04 first-snapshot inputs |
| E2-R005 | round.json, round_history, MANIFEST.sha256 | 1 | 0 | proposal_only: missing canonical D04 first-snapshot inputs |
| E2-R012 | round.json, round_history, MANIFEST.sha256 | 1 | 0 | proposal_only: missing canonical D04 first-snapshot inputs |
| E2-R014 | round.json, round_history, MANIFEST.sha256 | 2 | 1 | proposal_only: missing canonical D04 first-snapshot inputs |
| E2-R015 | round.json, round_history, MANIFEST.sha256 | 2 | 1 | proposal_only: missing canonical D04 first-snapshot inputs |
| E2-R016 | round.json, round_history, MANIFEST.sha256 | 1 | 0 | proposal_only: missing canonical D04 first-snapshot inputs |

## E2-R001

Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.
Failure evidence: no named error JSON was found; interpret retained logs only after independent review.
Batch log: `batch28.log` (1cbd8521a58abddd3352d2849c0c917c00264fbcfba1d9c4ca4dab37272f5457).
Batch-source candidates: `/data2/FreeToken/runs/plan_batches/batch28_E2-R001_python.sh` (16187660a994dd4b0d38557190fd1ff67c4842db4b3ef0ea33e90f205a25a1b1).
Service arm `A_cut_on_p1`: PID `1366727`, worktree `/data2/FreeToken/wt/e2base`, commit `23f2e2caa3395837c9474735ffc83321f3b9b5a1`; missing D04 service files: none.
Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.

## E2-R004

Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.
Failure evidence: no named error JSON was found; interpret retained logs only after independent review.
Batch log: no root `batch*.log` containing this round ID was found by this read-only scan.
Batch-source candidates: `/data2/FreeToken/runs/plan_batches/batch32_E2-R004_python.sh` (f61cb9a05837f52683c3d1a94139b8e47c9daab18b86f9b4b2cf58569859c596).
Service arm `P1`: PID `1728656`, worktree `/data2/FreeToken/wt/e2base`, commit `23f2e2caa3395837c9474735ffc83321f3b9b5a1`; missing D04 service files: none.
Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.

## E2-R005

Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.
Failure evidence: no named error JSON was found; interpret retained logs only after independent review.
Batch log: no root `batch*.log` containing this round ID was found by this read-only scan.
Batch-source candidates: `/data2/FreeToken/runs/plan_batches/batch33_E2-R005_python.sh` (4e57417b8169f5597241aa8e888e5b9bd85da0103e7df58ac422c65e561a539b).
Service arm `V0`: PID `1798593`, worktree `/data2/FreeToken/wt/e2base`, commit `23f2e2caa3395837c9474735ffc83321f3b9b5a1`; missing D04 service files: none.
Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.

## E2-R012

Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.
Failure evidence: `error.json` (71e67343da67def17afc9e7f01e7a5985b96657b8f89def7177176e00b652fb4).
Batch log: no root `batch*.log` containing this round ID was found by this read-only scan.
Batch-source candidates: `/data2/FreeToken/runs/plan_batches/batch41_E2-R012_python.sh` (805eef3029fa2186f76dd198d1540b5c389c01c70a42f4400ac6118705a6c408).
Service arm `B1`: PID `2628765`, worktree `None`, commit `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`; missing D04 service files: serve_args.txt.
Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.

## E2-R014

Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.
Failure evidence: `t04_phase2_error.json` (e44f63f77e55b2fcd281a35abf19d093230bc89288a80b835f92010b71c8c92b).
Batch log: `batch39.log` (e0927baa388441729d283a2108938afc400ba0d7c79cd305f5839cc0d25f1cb2).
Batch-source candidates: `/data2/FreeToken/runs/plan_batches/batch39_E2-R014_python.sh` (e9a575935cbcfc4eb9083918d10c8bde8336a656f645a6d6a1baf845c21b23df).
Service arm `candidate_boundary`: PID `2494304`, worktree `None`, commit `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`; missing D04 service files: none.
Service arm `restore`: PID `2510462`, worktree `None`, commit `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`; missing D04 service files: none.
Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.

## E2-R015

Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.
Failure evidence: `t04_phase2_error.json` (6bb8f4a1f717bafa4099053f20d6b682f6787b6c22d05a0ad39f4582d2a377a4).
Batch log: `batch43.log` (1ada760b9a2ee960a3d24259ecf03a9cc0e4f4c3fd6d3fa422c827f9483feda3).
Batch-source candidates: `/data2/FreeToken/runs/plan_batches/batch43_E2-R015_python.sh` (1e442030204ae7f0af5b5f03d8c629c8cba2f88dcf539715fa5b338f86891f6b).
Service arm `candidate_boundary`: PID `2749617`, worktree `None`, commit `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`; missing D04 service files: none.
Service arm `restore`: PID `2764428`, worktree `None`, commit `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`; missing D04 service files: none.
Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.

## E2-R016

Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.
Failure evidence: `error.json` (ad4070039f5298c91b819b9171d9d85d6fc212ed98049594396857b70f44ffdb).
Batch log: no root `batch*.log` containing this round ID was found by this read-only scan.
Batch-source candidates: `/data2/FreeToken/runs/plan_batches/batch42_E2-R016_python.sh` (3aba954c83b4a1048b5b030a4934fc5ca18d15e659eb002a780b9814c70143bf).
Service arm `B1`: PID `2673069`, worktree `None`, commit `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`; missing D04 service files: none.
Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.

## Boundary

A service may be described only where the retained command/log/arguments/environment evidence is present. Missing evidence remains a gap; this proposal does not infer service state or causal failure from absence.
