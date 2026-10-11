# D16 API SDK contract

The 01:30 night preauthorization permits only the current interleave scope:
six services and eight OpenAI Python SDK `/v1/completions` calls. Warm arms are
deferred because no existing evidence proves an actual expert-cache hit. This
directory holds the request/SSE SDK adapter and input closure; its paired thin
lifecycle adapter is in `development/r040i_api_d16/`. It has no native cache
collector, watchdog, benchmark loop, or D04 sealing implementation.

`sdk_completions.py` persists request, response headers, decoded chunks and
arrival times through a collection error. `interleave_input_binding.json` is a
CPU text mapping from sealed IDs; it does not prove worker token input, cache
state, physical batching, or original D16 internal equivalence.

`test_live_scope.py` is the service-time pytest entrypoint. It skips outside an
owned loopback service and, when supplied with the controller's environment,
executes the official SDK calls through `live_scope.py` and asserts the D16
completion contract.
