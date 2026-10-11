# E2-R040h / batch 116 D04 metadata preparation

Prepared-only terminal metadata. It records the independently reviewed failed_harness outcome without publishing a canonical round, manifest, pin, or history entry.

- Remote v1 preparation (preserved, rejected for canonical-ready shape): /data2/FreeToken/runs/dev_D16/r040h_b116_metadata_prepared_v1.json
- Remote v2 preparation: /data2/FreeToken/runs/dev_D16/r040h_b116_metadata_prepared_v2.json
- v2 SHA-256: 168aed56a43d544db452247bb8f06ffaaa95e3be2d4d3f4a773f784fdda53f89
- Independent review copy SHA-256: fcfacc6c48eb5a327d80fe5adc0451a925df46a0dcb81ebc04d381384083a67e
- Raw pre-closure inventory entries: 293
- Raw-inventory canonical JSON SHA-256: b8dd7ac612deb4440fe12f9f658cdc682dff368d3f06418bda4292a084a4f99a

v2 uses the ft_round/v2 skeleton and distinguishes one completed request generation from zero completed accepted scopes. It binds the actual shared foreign GPU lock observation (E2-R050a-gate-D15/batch118) without acting on it.

Root must independently review and invoke the existing generic append-only closing flow. This directory does not authorize publication.