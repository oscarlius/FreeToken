# R049 / T21 §13 prelaunch handoff

This is a new development-only runner. The earlier `r049_*` runner, tests,
and handoff remain frozen and are not inputs to this version's future startup
review.

## Fixed configuration

- Candidate: `988c9e183c8dca4415fd9b5d02318b26664da619`; parent measurement tree:
  `effb9969706922ddad9e59b96377e46469ebe97f`.
- T21 and its R046c source must both use `--memory-ratio 0.88`,
  `--kv-reserve-tokens 98304`, and `--max-seq-len-override 98304`.
- Route trace and the pause endpoint are disabled in all nine T21 arms.
  The runner rejects either inherited environment flag and trace CLI flags.
- R050 is an already-kept prerequisite. It is checked as kept and is never
  scheduled or rerun by this runner.

## R046c binding

The runner is intentionally blocked until an actual, sealed R046c result
exists. It accepts only `E2-R046c/manifest.json` with
`ft_r046c_route_manifest/v1`, candidate `effb996`, ratio `.88`, and the
98,304/2,048/96,256 window contract. Its only profile input is
`E2-R046c/G_seed12k/route`; `seed_45k`, `seed_real87100`, and two-decode are
held out. `seed_real87100` is replayed in full and ends naturally at the
96,256 prompt limit; it is never shortened.

No SHA is prewritten for the future R046c source, manifest, dry-run receipt,
or review. If an R046c repair changes any measurement-source file, create a
new R049 source version, rerun CPU proof, and bind the actual resulting SHA in
the later startup review.

## §13 comparison declaration

Each service directory receives `serve_args_diff.json`. Within production
(`L1/P1/PA1`, then `L2/P2/PA2`), the policy is the only scientific variable;
the profile and adaptation fields are declared required policy consequences.
Within diagnostics (`L_D0/P_D0/PA_D0`), the same rule applies with D0 common
to that diagnostic stratum. The file records the common `.88`, 98,304,
trace-off, and pause-off contract for every arm.

## Admission and safe CPU evidence

The default invocation is inert. `--dry-run` is Linux-only and must pass the
actual R046c measured closure, R050 kept closure, and sealed R046c manifest
before it creates only `.dryrun_E2-R049`; it dynamically reserves then closes
a loopback socket, rejects 8095, starts no service, sends no request, takes no
GPU lock, allocates no batch, and creates no formal RID. `--run` still requires
the dry receipt, startup review, owned controller receipt, and an idle GPU.

Do not execute a real dry run or startup while R057/R058 holds the GPU lock.
CPU tests prove source and guard behavior only. They do not prove a real
service startup, R046c route evidence, GPU memory, or T21 acceptance.

## Current execution blocker

The old T21 two-session probe requires the pause-gated `ft_dev` ACK protocol.
It cannot be used while §13 requires the pause endpoint off. R046c currently
supplies only an ordinary-SSE single-request client. This runner therefore
refuses `--run` before any batch allocation or GPU lock. A future ordinary-SSE
two-session client must preserve the normal `chatcmpl-{uid}` identity and
usage evidence; after it exists, create a new R049 source version and bind its
actual SHA in fresh CPU, dry-run, and startup-review evidence.
