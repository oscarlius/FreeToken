# Independent morning-report V3 startup review

## Verdict

PASS_STARTUP — root may launch the frozen CPU-only waiter. This review did not run the waiter or `--run`.

## Evidence

- `morning_report_readonly_v3.py` SHA-256 `e7d023b01e9452ca95d509453c9977f989900e1d0532f246a069036881566456`; inputs SHA-256 `9c371d2c23b4516f0f4a7b3e4c4281a0e686180c57e2fe39ecd3ed0d58b80cc6`; waiter SHA-256 `8d8f0d56499d3ec7aa0816e0f1a40a3e67e3f9da54cec31a4e426140283b84f6`.
- On `172.16.108.9`, all 15 frozen input pins passed from `/data2/FreeToken`; source, inputs, waiter, and CPU proof hashes match local copies.
- Remote owner identities match the frozen values: root `895116:167314480`, supervisor `895173:167314556`, service `895197:167314581`. The two future plan outputs and prior independent-review files were absent.
- Fresh CPU test run passed all seven cases. The supplied CPU proof also records a pre-09:00 dry attempt stopping at the wall-time guard without future files.
- V3 reads `until_epoch` from `start.json`, preserves the actual terminal/first issue, uses exclusive writes only after `--run`, and produces manual review instead of a clean-PASS claim when the terminal is `requires_review`/ineligible.
- The waiter rechecks source/input SHA, sleeps at most 30 seconds per step, waits at most 180 seconds for the real terminal, and invokes V3 once only.

## Gaps

- The real 09:00 terminal does not yet exist. This review does not predict or manufacture its result.

## Risks

- Any source/input hash change, missing terminal after the 180-second bound, or a guard failure must stop the waiter. No automatic push, waiver, or production action is authorized.
