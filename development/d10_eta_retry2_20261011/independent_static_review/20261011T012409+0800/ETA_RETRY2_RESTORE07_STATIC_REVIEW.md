# η retry2 / Restore07 static review

**Verdict: `REQUEST_CHANGES`.** No remote CPU, GPU, service, or API action was taken.

η correctly removes the unsupported stats CLI flag, parses the actual 481 offload arguments, partitions 367 rows across 48 layers, uses separate streams with a join, and computes 50-sample medians. It does **not** prove all hit routing: map tensors remaining unchanged after a graph replay are not proof that every fixed graph route ID resolves to a resident slot. Bind and verify real per-layer graph route IDs/slots and their disjointness from copy destinations before timing.

Restore07's twelve executable sources hash-match its manifest and differ from Restore06 only by normalized 06→07 identities. Its pending gates remain closed. Its approval scope text still says -06 and must be corrected to -07.
