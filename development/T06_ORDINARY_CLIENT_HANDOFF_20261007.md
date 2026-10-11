# T06 ordinary-client CPU preparation

`r046c_t06_ordinary_client_v1.py` is an external CPU tool for the R046c T06 path. It sends one normal `/v1/chat/completions` SSE request with `stream_options.include_usage=true`; it refuses `FT_DEV_PAUSE_ENDPOINT=1` and fails if an `ft_dev` ACK appears. It writes normal SSE `chatcmpl-{uid}` identity, API usage, input-byte SHA, and raw SSE SHA.

`--bind` then requires that same UID in D0 `reqs` records (`rid`, `new_tokens`, `cached_tokens`) and in route records parsed by the existing frozen `e2base1/scripts/route_analyze.py`. It requires route prefill tokens = D0 new tokens, D0 new + cached = API prompt usage, and D0 cached = API cached usage. The binding record retains source hashes for input, API record, D0, canonical matched D0 schedule, every matched route record, and the parser.

The result deliberately remains `uid_bound_not_token_index_bound`. Normal SSE usage exposes totals only; the current D0 and route records expose UID token totals but no output `request_seq`. T06 cannot reuse old pause ACK acceptance or infer it from chunk counts. The minimum backend/observer fields for that assertion are `uid`, `request_seq`, `completion_tokens_delta`, and `completion_tokens_cumulative`, captured from a real normal request without pause. This tool does not implement those fields or manufacture equivalent proof.

CPU verification: `python -m pytest development/tests/test_r046c_t06_ordinary_client_v1.py -q` passed 4 tests. They cover strict four-artifact/hash binding, UID/usage mismatch rejection, ordinary-SSE ACK rejection, and an ephemeral dynamic socket guard that never listens or selects 8095. No service, GPU, HTTP request, pause endpoint, or product source was run or changed.

R046c integration must run a new real FILEDRY/ordinary service test with route trace as separately authorized, preserve the raw artifacts above, and obtain the required R startup review. This CPU preparation is not a T06 measurement or acceptance result.
