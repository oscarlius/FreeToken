# Input binding — strict replay attempt

Created after raw remote read; append-only.

- Raw round: `/data2/_shared/runs/ft_rounds/E2-D09-T17-reapply-bd57-20261010/round.json`
  - SHA-256: `a6655b5920069ada590f515dc0a612e8fb65b33045c48ba56021b235b4750ee5`
- Candidate commit: `bd57cfdccc2a935d46cb0a89b8b36be7a18706de`.
- Raw target response: `services/hot_c0_p20282_t1020/call_4.response.json`
  - SHA-256: `d5cd03d3571011025694508fa43ba7f2e15fb9c69104386555921786f45f56f9`
  - Observed usage: prompt 21302, cached 20160, completion 32.
- Raw target binding: `services/hot_c0_p20282_t1020/call_4.binding.json`
  - SHA-256: `818b87b48328070aecbdfa530ce7521383d122f510c7cdf0f9d7d6712ba455fb`.
- Existing D05 method source SHA-256: `3847cd829ad93ee01fffe82c60e16cbfc404ba02626b29313c28295e5736e71c`.

Strict replacement rule: no direct mutation of request cached length, device length, cache result, or scheduler predicate. Only model token/sample side effects may be substituted after real Scheduler construction and bookkeeping are shown.