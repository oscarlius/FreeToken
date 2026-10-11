"""v5.8: decode bounds by execution structure, replacing the empirical "30 tok/s per lane" reference.

Per-step resources for B lanes (one token per lane per step):
  GPU serial part      F(B, L) = t0 + k*L + t_req*(B-1)                  (paper §4.3/§4.7 fit)
  misses over PCIe     B * m_link * S / B_P                             (S = 480 experts x 2.77 MB)
  misses on the CPU    A_cpu + B * m_cpu * S / B_C                      (fitted on HR window01)
Serial structure: times add. Ideal staggered overlap: the slowest resource bounds the step.
Run: python paper/src/theory_v58.py
"""
T0_MS, K_MS_PER_KTOK, T_REQ_MS = 13.1, 0.032, 5.3
S_BYTES = 1_330_790_400                       # 480 NVFP4 experts (R046g D0 step-0 h2d bytes)
S_TOK_MS = 54.77                              # PCIe time of S (paper §4.3), i.e. B_P = 24.3 GB/s
B_P = S_BYTES / (S_TOK_MS / 1e3)
L_KTOK = 1.2                                  # X group prompts (1,179 / 1,231 tokens)
M_TWO = 0.3824                                # two distinct lanes, 2,700 LRU slots (closed-loop X, D0)
M_ONE = 0.3508                                # single lane X lane0 (retry2 D0)
D15_STATIC_PENALTY = (0.115, 0.160)           # static expert set vs LRU, D15 held-out replay


def f_ms(lanes):
    return T0_MS + K_MS_PER_KTOK * L_KTOK + T_REQ_MS * (lanes - 1)


def cpu_fit(single_tps, two_tps):
    """t(B) = A + B*S/B_C from the fetch-0 services (every routed expert on the CPU)."""
    t1, t2 = 1e3 / single_tps, 1e3 / two_tps
    per_lane_ms = t2 - t1
    return t1 - per_lane_ms, S_BYTES / (per_lane_ms / 1e3)


def main():
    print(f"B_P = {B_P / 1e9:.1f} GB/s, F(1) = {f_ms(1):.2f} ms, F(2) = {f_ms(2):.2f} ms")
    a_fp32, bc_fp32 = cpu_fit(28.61, 18.91)        # HR-b (NO_VNNI, fp32), window01 S4
    a_w4a8, bc_w4a8 = cpu_fit(18.05, 11.20)        # HR-a (W4A8), window01 S3
    print(f"CPU path fp32: A = {a_fp32:.2f} ms, B_C = {bc_fp32 / 1e9:.1f} GB/s "
          f"({bc_fp32 / B_P:.1f}x PCIe); W4A8: A = {a_w4a8:.2f} ms, B_C = {bc_w4a8 / 1e9:.1f} GB/s")

    rows = []
    x2 = 2 * M_TWO * S_TOK_MS
    rows.append(("offload serial (production)", 1e3 / (f_ms(2) + x2), "16.84-16.97"))
    rows.append(("offload ideal overlap (M4), link bound", 1e3 / max(f_ms(2), x2), "-"))
    rows.append(("fetch 0, all experts on CPU, fp32 (HR-b)", 1e3 / (a_fp32 + 2 * S_BYTES / bc_fp32 * 1e3), "18.86-18.96"))
    for pen in D15_STATIC_PENALTY:
        m_s = M_TWO + pen
        t = a_fp32 + 2 * m_s * S_BYTES / bc_fp32 * 1e3
        rows.append((f"static GPU set + CPU fp32, m_s={m_s:.1%}", 1e3 / t, "-"))
    rows.append(("GPU roof, no misses", 1e3 / f_ms(2), "-"))
    print("\nTwo distinct lanes, per lane (tok/s):")
    for name, v, meas in rows:
        print(f"  {name:48s} {v:6.1f}   measured {meas}")

    # W4A8 dynamic-fetch hybrid (window02 default): check how far the CPU-path model lands.
    fetch_share, m_h = 0.249, 0.431
    t = a_w4a8 + 2 * m_h * (1 - fetch_share) * S_BYTES / bc_w4a8 * 1e3
    print(f"\nModel check, default hybrid (W4A8, fetch {fetch_share:.0%}, m={m_h:.1%}): "
          f"{1e3 / t:.1f} vs measured 25.96-26.27 ({1e3 / t / 26.1:.0%})")

    print("\nSingle lane (tok/s):")
    print(f"  offload serial: {1e3 / (f_ms(1) + M_ONE * S_TOK_MS):.1f} (measured 29.62-30.19)")
    for pen in D15_STATIC_PENALTY:
        m_s = M_ONE + pen
        print(f"  static GPU set + CPU fp32, m_s={m_s:.1%}: {1e3 / (a_fp32 + m_s * S_BYTES / bc_fp32 * 1e3):.1f}")
    print(f"  GPU roof: {1e3 / f_ms(1):.1f}")
    print(f"\nMiss rate at which the offload link bound reaches a given per-lane rate R (two lanes): "
          f"m = B_P / (2 R S); R=23.9 -> {B_P / (2 * 23.9 * S_BYTES):.1%}")


if __name__ == "__main__":
    main()
