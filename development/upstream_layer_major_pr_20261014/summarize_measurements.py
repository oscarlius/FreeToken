"""Summarize only pre-registered completed requests; keep lifecycle failure intact."""
import datetime
import hashlib
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
RAW=HERE/'gpu_evidence'
labels=('long2-cold32012','long3-cold32012')
summary={'created_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
         'main':'9c635a157798da4aa43e6d051e92620521ed1858',
         'candidate':'63858faa584ddd623d5ea1728e26270e0c7f649b',
         'scored_labels':labels,'ttft_operator':'HTTP first nonempty completion text',
         'tokens_per_second_operator':'128 output tokens / full HTTP response seconds',
         'original_window_classification':json.loads((RAW/'GPU_WINDOW_TERMINAL.json').read_text())['classification'],
         'recovery':json.loads((RAW/'GPU_WINDOW_RECOVERY.json').read_text()),'arms':{}}
all_records={}
for arm in ('main','candidate_off','candidate_on'):
    rows=[json.loads(line) for line in (RAW/'gpu_results'/arm/'receipts.jsonl').read_text().splitlines()]
    assert len(rows)==9 and all(x['ok'] and len(x['native_token_ids'])==128 for x in rows)
    all_records[arm]={x['label']:x for x in rows}
    chosen=[all_records[arm][label] for label in labels]
    summary['arms'][arm]={'calls':9,'cold_ttft_seconds':[x['ttft_seconds'] for x in chosen],
        'cold_wall_seconds':[x['wall_seconds'] for x in chosen],
        'median_cold_ttft_seconds':statistics.median(x['ttft_seconds'] for x in chosen),
        'median_cold_wall_seconds':statistics.median(x['wall_seconds'] for x in chosen),
        'median_e2e_output_tps':statistics.median(128/x['wall_seconds'] for x in chosen),
        'continuation_cached_tokens':[x['native_cached_tokens'] for x in rows if 'continuation' in x['label']]}
for arm in ('candidate_off','candidate_on'):
    assert set(all_records[arm])==set(all_records['main'])
    assert all(all_records[arm][name]['native_token_ids']==reference['native_token_ids']
               for name,reference in all_records['main'].items())
base=summary['arms']['main']['median_cold_ttft_seconds']
enabled=summary['arms']['candidate_on']['median_cold_ttft_seconds']
summary.update(native_id_equality='all9labels,128IDs each,acrossall3arms',
               ttft_speedup=base/enabled,ttft_reduction_percent=(1-enabled/base)*100,
               h2d_bytes_measured=False,vram_peak_measured=False,
               evidence_manifest_sha256=hashlib.sha256((HERE/'GPU_EVIDENCE_MANIFEST.json').read_bytes()).hexdigest())
(HERE/'MEASUREMENT_SUMMARY.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
review={'reviewer':'native subagent /root/layer_major_review','verdict':'COMMENT',
        'remaining_measured_arm_blockers':0,
        'scope':'90manifest-bound artifacts, source/argv, native/SSE accounting, timings, E3recovery and45minbudget',
        'caveat':'Original lifecycle remains failed_harness; valid completed timed arms are separate; no H2D or VRAMpeak claim',
        'observations':['27completed requests,128tokens,length; allnativeIDs equal',
                        'main/off21x4096plus3x3340;on3x32012prefill batches',
                        'Scoredlong2/long3 only;long1unscoredJIT',
                        'Recovery2SDKcalls,1passed0skipped, elapsed29m14s']}
(HERE/'INDEPENDENT_GPU_REVIEW.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
text=f'''# Layer-major 上游贡献：测量结论

候选：`{summary['candidate']}`；main：`{summary['main']}`。三个服务串行，共27次生成，每次128token，所有9个标签的原始生成ID跨三臂一致；三组续算各命中32000token、重算77token。

| 臂 | 冷32K TTFT中位数 | 128token整轮中位数 | 端到端输出tok/s中位数 |
|---|---:|---:|---:|
'''
for arm,value in summary['arms'].items():
    text+=f"| {arm} | {value['median_cold_ttft_seconds']:.4f}s | {value['median_cold_wall_seconds']:.4f}s | {value['median_e2e_output_tps']:.4f} |\n"
text+=f'''
TTFT按HTTP首个非空completion文本计。仅long2/long3两个预登记冷样本计成绩，long1整组用于形状JIT预热。开启后相对固定main的TTFT减少{summary['ttft_reduction_percent']:.2f}%，为{summary['ttft_speedup']:.3f}倍；这些是两个合成样本，不能扩张为普遍收益或统计置信结论。端到端输出tok/s含预填，不是稳态解码速度。未测H2D字节和显存峰值。

原窗口在全部测量结束后的即时GPU空闲检查中判`failed_harness`，原终态保留。后续只读复核GPU空闲后，续接原授权的E3恢复；没有重跑测量。E3自身冻结参照的2次SDK冒烟通过（1 passed、0 skipped），恢复在11:22:30完成，整窗29分14秒，未超45分钟。非作者复核认可每臂已完成测量可用于有边界的PR证据，原生命周期失败须在PR中如实说明。
'''
(HERE/'RESULT.md').write_text(text,encoding='utf-8')
print(json.dumps({key:summary[key] for key in ('ttft_speedup','ttft_reduction_percent','native_id_equality','original_window_classification')},indent=2))
