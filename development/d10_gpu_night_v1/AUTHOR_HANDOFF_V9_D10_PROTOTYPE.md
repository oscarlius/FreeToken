# D10 prototype v3 handoff

`d10_prototype_owned_parent_v3.py` is the runnable parent-owned path for
`E2-D10-PROTOTYPE-night-20261010`.  It uses the established D07 atomic batch
reservation and child-birth receipt protocol, validates the exact candidate,
native reuse receipt and sealed D09 terminal bindings before GPU ownership,
then starts one service and runs four frozen AIPerf profiles for eight calls.

The root admission must bind the v4 AIPerf admission fields plus
`prototype_rid`, candidate/parent, native provenance digest, and one exact
service object (`argv`, `cwd`, loopback endpoint, API and tcpstore ports) and
`prototype_output`.  The service argv must contain `--d10-staggered-decode`.

The wrapper installs the external one-event observer inside the actual server
process.  Completion requires the branch event for two eligible lanes, four
successful profile exports, and exact post-cleanup rebind of both admission
ports.  Any missing proof is written as `not_met` or `failed_harness`; failed
cleanup retains the D07 lock.  This prototype is not a T16 verdict or product
acceptance; the reviewer-owned `night_strata_result_review_v2` remains the
only terminal reviewer.
