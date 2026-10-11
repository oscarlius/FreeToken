"""v5.5 recomputation: content-specific miss rates, L*, the M3 cost correction and the Strata gap split.

Serial decode model (paper §4.3/§4.7): t_step = t0 + k*L + m * S_TOK_MS, with S_TOK_MS the PCIe time of a
step whose 480 active experts (48 layers x 10) all miss. Run: python paper/src/theory_v55.py
"""
T0_MS, K_MS_PER_KTOK = 13.1, 0.032
EXPERT_BYTES_NVFP4 = 1_330_790_400 / 480        # R046g D0 step-0 h2d_bytes / 480 missing experts
B_PCIE = EXPERT_BYTES_NVFP4 / 0.1141e-3          # bytes/s implied by S_TOK_MS / 480
S_TOK_MS = 480 * EXPERT_BYTES_NVFP4 / B_PCIE * 1e3


def r_serial(m, l_ktok):
    return 1000 / (T0_MS + K_MS_PER_KTOK * l_ktok + m * S_TOK_MS)


def content_table():
    rows = [("single 32K synthetic (b163)", 0.2527, 32.064, (35.42, 35.64)),
            ("single 1.2K X lane0 (retry2 offload)", 0.3508, 1.179, (30.17,)),
            ("single 87-95K seed_real W98K", 0.3859, 90.5, (28.045,)),
            ("single 87-95K seed_real W128K", 0.4138, 90.5, (26.867,))]
    for name, m, l, measured in rows:
        r = r_serial(m, l)
        print(f"{name:40s} m={m:.4f} theory={r:5.1f} measured={measured} ratio="
              + "/".join(f"{x / r:.1%}" for x in measured))


def l_star():
    for m in (0.2193, 0.2413, 0.3859):
        print(f"L* at m={m:.4f}: {512 / (10 * m):.0f}")


def m3_cost():
    x_ms, f_ms = 0.3859 * S_TOK_MS, T0_MS
    for label, t_pass, c in (("warm", 2.8, x_ms / 1e3), ("cold87K", 18.0, f_ms / 1e3)):
        for gap in (0.5, 0.2):
            k = 0
            while (t_pass + k * c) / (k + 1) > gap:
                k += 1
            print(f"M3 {label} gap<={gap}s: k={k} T'={t_pass + k * c:.2f}s (+{k * c / t_pass:.1%})")
        print(f"M3 {label} amplification at r=10: {1 / (1 - 10 * c):.2f}")


def strata_split():
    strata_expert = 17.45 * 2**30 / 9196
    print(f"IQ3_S expert {strata_expert / 1e6:.2f} MB vs NVFP4 {EXPERT_BYTES_NVFP4 / 1e6:.2f} MB "
          f"({strata_expert / EXPERT_BYTES_NVFP4 - 1:+.1%})")
    m_ft, f_ft = 0.2527, T0_MS + K_MS_PER_KTOK * 32.064
    x_ft = m_ft * S_TOK_MS
    print(f"FreeToken offload 32K: {f_ft:.2f} + {x_ft:.2f} = {f_ft + x_ft:.2f} ms ({1000 / (f_ft + x_ft):.1f} tok/s)")
    x_iq = x_ft * strata_expert / EXPERT_BYTES_NVFP4
    print(f"  bytes-only (IQ3_S) in PCIe structure: {f_ft + x_iq:.2f} ms ({1000 / (f_ft + x_iq):.1f} tok/s)")
    # Strata per-CPU-expert cost from its three short-prompt requests (hit rate -> tok/s)
    pts = [(1 - 0.658, 66.4), (1 - 0.634, 64.6), (1 - 0.617, 60.6)]
    xs = [m * 480 for m, _ in pts]
    ys = [1000 / v for _, v in pts]
    mx, my = sum(xs) / 3, sum(ys) / 3
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    print(f"Strata marginal cost per CPU expert: {slope:.3f} ms ({strata_expert / (slope * 1e-3) / 1e9:.0f} GB/s), "
          f"intercept {my - slope * mx:.1f} ms")
    cpu_nvfp4 = EXPERT_BYTES_NVFP4 / (strata_expert / slope)
    misses = m_ft * 480
    print(f"  overlap structure, NVFP4 at Strata efficiency: CPU part {misses * cpu_nvfp4:.1f} ms vs GPU fixed {f_ft:.1f} ms")


if __name__ == "__main__":
    content_table()
    l_star()
    m3_cost()
    strata_split()
