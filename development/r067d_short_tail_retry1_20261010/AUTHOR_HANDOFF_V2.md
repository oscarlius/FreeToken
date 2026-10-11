# R067d retry1 V2 CPU handoff

V1 remains immutable. Its configured environment has forty stale original-v1
filesystem bindings; the V1 child checks those bindings before it can call its
environment renderer or `Popen`. `CPU_FAILURE_ADMISSION_RETRACTION_V2.json`
therefore classifies the condition as CPU packet not ready before reservation,
launch, service, HTTP call, or GPU work. It consumes neither a service nor a
retry budget.

V2 retains config SHA-256
`88a587c598cf53d0465d99e50d48286621ad0ed9b2313001fea5ca23482a8d92`,
V1 packet SHA-256
`700931c266165954aed43ef98c2a8ee3568dc4a45c6f4f409eff52f88f8d7b14`,
and uses packet SHA-256
`6a32a526b4190fc60ce102f320123a0182ddb5a29c9ce1dcbe91074b56f76237`.
Only the prepared child's preflight and its Popen path render the four runtime
filesystem environment values into each new retry1 service directory.

Linux CPU receipt SHA-256:
`e7a1ce9e26bcff2f3a380c808a5a651eac2746e90e9454410e9914e9ab804038`.
The exact child functions `verify_runtime_environment`,
`start_prepared_service`, and `judge_prepared_window` were extracted from that
packet and invoked. It records 10 passed runtime-environment guards, 10 fake
Popen calls carrying the rendered environment, 14 valid synthetic window
judgments, and zero real HTTP, service, or GPU actions. This is CPU-only and
does not admit a GPU round.
