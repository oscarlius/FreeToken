"""遍数排队模型：每请求一遍（FIFO, M/D/1） vs 按遍合批（bulk service）。
纯推算，常数取自轮次库：D=2.66 s（短后缀一遍，E1-R003），P/B_P=2.80 s，m*S_tok=0.292 GB，B_P=24.3 GB/s。"""
import random, statistics as st, math
D=2.66; BP=24.3; MS=0.292
def sim(lam, policy, n=200000, seed=1, cap=None):
    """cap: 每遍最多收走的请求数（None = 无限，理想化）。"""
    rnd=random.Random(seed); t=0; arr=[]
    for _ in range(n):
        t+=rnd.expovariate(lam); arr.append(t)
    ttft=[]; busy=0.0; free_at=0.0; i=0; passes=0
    if policy=='fifo':
        for a in arr:
            s=max(a,free_at); free_at=s+D; ttft.append(free_at-a); busy+=D; passes+=1
    else:  # bulk: 一遍开始时收走已到达请求（至多 cap 个）
        while i<len(arr):
            s=max(arr[i],free_at); j=i
            while j<len(arr) and arr[j]<=s and (cap is None or j-i<cap): j+=1
            free_at=s+D; passes+=1; busy+=D
            for k in range(i,j): ttft.append(free_at-arr[k])
            i=j
    T=arr[-1]
    q=sorted(ttft); p95=q[int(.95*len(q))]
    return st.mean(ttft), p95, busy/T, passes/T
import sys
if '--figure-grid' in sys.argv:
    # 论文 v4.0 图 4 的数据：n=60000，seed=5，λ 网格与容量 1/2/4/不限
    grid = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.8)
    for cap in (1, 2, 4, None):
        row = []
        for lam in grid:
            if lam * D / (cap or 1e9) >= 0.95:
                row.append(None); continue
            _, p95, _, _ = sim(lam, 'bulk', n=60000, seed=5, cap=cap)
            row.append(round(p95, 2))
        print(cap or 'inf', row)
    sys.exit(0)
print('lam(轮/s) | FIFO 均值/P95/PCIe占比 | 合批 均值/P95/PCIe占比 | 合批后解码余量(tok/s)')
for lam in [0.05,0.1,0.2,0.3,0.35,0.5,1.0]:
    rho=lam*D
    f=sim(lam,'fifo') if rho<0.97 else None
    b=sim(lam,'bulk')
    mdl = D+rho*D/(2*(1-rho)) if rho<1 else float('inf')
    fs = '%.2f/%.2f/%.0f%% (MD1式 %.2f)'%(f[0],f[1],f[2]*100,mdl) if f else '不稳定 ρ=%.2f'%rho
    print('%.2f | %s | %.2f/%.2f/%.0f%% | %.0f'%(lam,fs,b[0],b[1],b[2]*100,(1-b[2])*BP/MS))
print('\n有限合批容量（每遍至多 cap 个请求），均值/P95：')
print('cap | lam=0.3 | lam=0.5 | lam=0.8')
for cap in (1,2,4,None):
    row=[]
    for lam in (0.3,0.5,0.8):
        if lam*D/(cap or 1e9)>=0.98: row.append('不稳定'); continue
        m_,p_,_,_=sim(lam,'bulk',n=100000,seed=3,cap=cap); row.append('%.2f/%.2f'%(m_,p_))
    print('%s | %s'%(cap or '∞',' | '.join(row)))
print('\nPCIe 限制的解码总量条件上界 (u=0): %.1f tok/s；8 路每路 30 需每 token 未命中 <= %.0f MB'%(BP/MS,BP/240*1000))
# 两路解码：串行 vs 理想错相位重叠
nt=13.1+0.032*32+5.3; tr=2*MS*1000/BP
print('B=2: 串行 %.1f ms -> %.1f tok/s/路；重叠 max=%.1f ms -> %.1f tok/s/路；每路30只需 PCIe %.1f GB/s (u<=%.0f%%)'%(
    nt+tr,1000/(nt+tr),max(nt,tr),1000/max(nt,tr),60*MS,100*(1-60*MS/BP)))
# D6：干扰期其他会话保持 r tok/s 时，预填时间放大倍数（每步 26 ms）
print('D6 预填放大: '+', '.join('r=%d:x%.2f'%(r,1/(1-r*0.026)) for r in (1,5,10,20,30)))
# 64K 只靠 MoE 提速：所需等效算力（每 token 约 4.72 GFLOP × 65,412 ≈ 309 TFLOP，BF16 峰值 165）
for nm in (8.1,9.7):
    bud=10-nm-0.2; print('64K 非MoE %.1f s: MoE 预算 %.2f s -> 需 %.0f TFLOPS'%(nm,bud,309/bud))
# 双会话每路 30 tok/s 所需未命中处理带宽
for m in (0.2193,0.3047):
    need=2*m*1331/(1000/30-13.1-1.05-5.3)   # MB/ms = GB/s
    print('m=%.4f: B=2 每路30 需 BW>=%.1f GB/s, CPU 需补 %.1f GB/s'%(m,need,need-BP))
# 短后缀按路由搬运的比例
for n in (8,19,32,64,128,256,512):
    f=1-(1-10/512)**n; print('n=%d 用到专家比例 %.1f%% 推算一遍 %.2f s'%(n,100*f,f*2.80))
# 断点：多切一段 vs 多算 token
for c in (0.175,0.2): print('break-even tokens @%.3f s/k: %.1fK'%(c,2.80/c))
# 冷预填 ≤10 s 上限
a,b,c0=0.0002,0.175,0.2
print('cold<=10s N=%.1fK'%((-b+math.sqrt(b*b+4*a*(10-c0)))/(2*a)))
for N in (32.768,65.412): print('T(%.1fK)=%.2f s'%(N,a*N*N+b*N+c0))
