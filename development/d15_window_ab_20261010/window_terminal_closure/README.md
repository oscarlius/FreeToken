# D15 WINDOW AB canonical closure

This package is an inert archive helper for the completed two-service Window A/B run. It accepts only the sealed independent review whose SHA-256 is recorded in `close_window_ab.py`, recomputes both original raw-artifact maps, and preserves the original `failed_harness` carrier plus the resume `not_met` carrier.

It performs no GPU, service, HTTP, lock, or source action. The formal archive deliberately does not query current production state: its cleanup claim is limited to hash-bound historical receipts. Per-service raw argv/environment dumps were absent, so the formal required fields explicitly record that absence instead of fabricating reconstructed values.
