"""Produce v5.2 with changes confined to section 8 and its version label."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old = ROOT / "paper/src/body_v51.html"
    baseline = {str(p.relative_to(ROOT)): digest(p) for p in [
        old, ROOT / "paper/src/build_v51.py", ROOT / "paper/src/figures_v51.py",
        ROOT / "paper/FreeToken_MultiGPU_CoExec_v5.1.html",
        ROOT / "plan/data_releases/FTD-20261009-1.json",
    ]}
    body = old.read_text(encoding="utf-8")
    original_section = body.split('<section id="s8">', 1)[1].split('</section>', 1)[0]
    section = original_section.replace('8 目标可达性 <span class="ev d">推导</span>',
        '8 目标可达性 <span class="ev d">推导</span> / <span class="ev m">实测</span>')
    section = section.replace('未测；串行模型推算 21–23', 'R045：22.03–22.53 tok/s，4请求均未达标；串行模型21–23')
    result = json.loads((ROOT / "development/r045_production_aiperf_20261009/R045_RESULT.json").read_text(encoding="utf-8"))
    rows = []
    for row in result['rows']:
        cache = 'API缺失 / native0' if row['api_cached_tokens'] is None else 'API64 / native64'
        rows.append(f"<tr><td>{row['wave']} / {row['request_id'][:8]}</td><td>{row['decode_tok_s']:.3f}</td><td>{row['ttft_ms']/1000:.3f}</td><td>{row['ttfo_ms']/1000:.3f}</td><td>{row['usage']['completion_tokens']}</td><td>{cache}</td></tr>")
    addition = '''
<h3>8.1 R045 两路解码对照 <span class="ev m">实测</span></h3>
<p>候选 <code>481d3a7</code>、AIPerf 0.11.0、两条冻结短提示、并发2、两组共4请求，逐请求解码吞吐为22.03–22.53 tok/s，均低于每路严格 &gt;30 的目标，终态 <code>not_met</code>。它与§4.4串行模型约23 tok/s吻合，未证明错相位重叠收益。短提示与模型的32K情景不同，吻合仅作该负载的观察，不是参数普适验证。<a href="../development/R045_RESULT_20261009.md">〔R045独立结果，新增于FTD-20261009-1之后〕</a></p>
<table class="booktabs small"><caption>表12c R045逐请求结果</caption><thead><tr><th>组 / 请求</th><th>decode tok/s</th><th>TTFT s</th><th>TTFO s</th><th>实际输出token</th><th>缓存</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table>
<p>TTFT取首个非空delta（含reasoning），TTFO取首个正文；解码指标含reasoning并排除TTFT。输出上限128、temperature0、top_p1、ignore_eos=false，实际提前EOS为46/58，按实际usage计算，不能按128虚算。首组API缓存字段缺失保留null、native为0；第二组各命中64，不称无缓存重复。请求区间重叠及native running-req2不能替代计算重叠或状态隔离证明。</p>
<p>后续D10只按已批准范围做可行性原型，复用本负载并增加ignore_eos=true的256 token对照；其预测和实测另行封存，尚无结果。C5的hybrid措辞等待R002-mini无MTP对照，本版保持原文；无MTP速度未测，多卡仍属推导 / 方案。</p>
'''
    section += addition
    new = body.replace(original_section, section, 1).replace('预印本草稿 · v5.1 ·', '预印本草稿 · v5.2 ·', 1)
    newpath = ROOT / 'paper/src/body_v52.html'
    newpath.write_text(new, encoding="utf-8", newline="\n")
    subprocess.run([sys.executable, str(ROOT / 'paper/src/build_v52.py')], check=True)
    restored = new.replace(section, original_section, 1).replace('预印本草稿 · v5.2 ·', '预印本草稿 · v5.1 ·', 1)
    assert restored == body, 'Unexpected out-of-scope body change'
    assert all(digest(ROOT / p) == sha for p, sha in baseline.items())
    evidence = {
        'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'scope': 'section8_plus_version_metadata_only_C5_unchanged',
        'baseline_unchanged': baseline,
        'output_sha256': digest(ROOT / 'paper/FreeToken_MultiGPU_CoExec_v5.2.html'),
        'r045_result_sha256': digest(ROOT / 'development/r045_production_aiperf_20261009/R045_RESULT.json'),
        'body_scope_check': 'PASS', 'model_calls': 0, 'gpu_calls': 0,
    }
    (HERE / 'PAPER_SCOPE_CHECK.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
