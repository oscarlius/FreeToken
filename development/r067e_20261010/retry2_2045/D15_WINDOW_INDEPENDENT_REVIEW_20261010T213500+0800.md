# D15 Window Independent Review

Status: **REQUEST_CHANGES**.

Remote CPU validation passed: 11 tests in 1.19 seconds. The CUDA-hidden observer proof installed the current observer's Engine constructor and `forward_batch` hooks without CUDA initialization.

The serial two-service flow, frozen A equality stop, B09/capacity gate, D0 rejection, 481 pin, deferred sampler, and unsafe-cleanup lock retention are present.

`window_runner.invoke()` still polls prefill events for up to two seconds after the SSE thread returns, using `time.monotonic() + 2` instead of the absolute measurement deadline. It then binds/parses response data without another deadline check. This can exceed the stated 1800-second measurement limit outside the documented cleanup allowance. Clamp this polling to the deadline and fail before post-deadline parsing, then refresh pins and re-review.
