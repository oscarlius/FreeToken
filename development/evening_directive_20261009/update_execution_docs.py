"""Archive old card bytes and apply the approved evening scope with real times."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import stat

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(path):
    target = HERE / 'prior_docs' / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(path.read_bytes())


def main():
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    d10 = ROOT / 'development/d10_staggered_20261009/prediction_manifest.json'
    seal = {'sealed_at': now, 'file': str(d10.relative_to(ROOT)), 'sha256': sha(d10),
            'measurement_started': False, 'status': 'sealed_before_measurement'}
    sealpath = d10.with_name('PREDICTION_SEAL.json')
    if not sealpath.exists():
        sealpath.write_text(json.dumps(seal, indent=2) + '\n', encoding='utf-8')
        d10.chmod(stat.S_IREAD)
        sealpath.chmod(stat.S_IREAD)
    else:
        seal = json.loads(sealpath.read_text(encoding='utf-8'))
        assert sha(d10) == seal['sha256']
    d09card = ROOT / 'plan/02_开发任务/D09_机制D3_基于577的层优先触发点.md'
    d10card = ROOT / 'plan/02_开发任务/D10_机制D14_错相位重叠解码可行性原型.md'
    archive(d09card)
    archive(d10card)
    d09card.write_text(f'''# D09 消息边界检查点（论文 M1 第二步）

最后写入：{now}。用户10-09晚间已批准，覆盖旧卡多锚点扩面范围；旧卡原字节位于 `development/evening_directive_20261009/prior_docs/`。

| 项 | 当前要求 |
|---|---|
| 工期 | 3–4人日 |
| 基点 | 481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9 |
| 分支 / 独立工作树 | codex/d09-message-boundary-v1 / development/e2d09-message-boundary-v1 |
| 范围 | 上一轮消息边界多存一个检查点；前缀≥8192且尾段≤1024时生效 |
| 存储 | 复用#577主存槽；prompt-cache-tail可选第二锚；不扩展为任意多锚点 |
| 默认 | 关闭；release/e2保持隔离 |
| GPU顺序 | 10-10 09:00观察报告→推送申请→R067d→R047/T03b→本卡→D10 |

## 开发前预测门

论文§4预测：目前两遍约5.6秒的合格短尾轮次，开启后应为一遍约2.8秒；以首次非空delta（含reasoning）的首token延迟为口径。必须先列受影响T2轮号、准确消息边界前缀与尾段、基线TTFT、预测TTFT并取得SHA封存，才实现本机制；测后逐轮列差值及偏差原因。

已有T2原始回放下载到 `development/d09_prediction_20261009/source/`，逐件绑定远端SHA。C_edit的两遍候选为行5、6、7、8、10（5.341/5.425/5.376/5.381/5.324秒），**仅是候选，不能在未按目标tokenizer验证前缀/尾段时全部列作受影响轮次**。C_warm约2.7秒是已有一遍控制；逆序首轮完整冷重算8–12秒不是上述两遍短尾基线。相邻轨迹轮次相差assistant/tool两条消息，不能当作单消息边界。

预测状态以 `development/d09_prediction_20261009/` 独立预测文件和封存回执为准；未封存前不修改引擎。待取得最终封存后，将SHA及逐轮预测追加本卡。

## 验收

- T16默认关闭逐位一致。
- T17同结构等价，必须包含本卡新增切分；尾段≤64结论以R067d为准。
- T03b编辑回放。
- Agent T2倒序冷、升序热、编辑三趟逐轮首token与预测对照。

当前仅隔离树及预测证据准备；不记GPU通过或收益兑现。
''', encoding='utf-8')
    d10card.write_text(f'''# D10 错相位重叠解码可行性原型

最后写入：{now}。用户10-09晚间已批准，仅3–5人日可行性原型；旧卡原字节保留。

| 项 | 当前要求 |
|---|---|
| 分支 / 工作树 | codex/d10-staggered-v1 / development/e2d10-staggered-v1，基于481d3a7 |
| 默认 | 关闭，独立工作树 |
| CPU / GPU | CPU可与D09并行；GPU严格在D09验收之后 |
| 测量 | R045原两条冻结提示、同AIPerf0.11配置，另加ignore_eos=true、256token版本 |
| 正式开发门 | 每路严格>30 tok/s且T16通过；未满足如实记负结果并入论文 |

## 测量前预测（已封存）

预测文件：`development/d10_staggered_20261009/prediction_manifest.json`。

SHA256：`{seal['sha256']}`。封存回执：`PREDICTION_SEAL.json`；封存时间{seal['sealed_at']}。

§4.4旧系数串行43.4ms；理想重叠24.0–28.2ms，即每路35.46–41.67tok/s，理想端约41。R045四个实测速率折成步长44.383–45.392ms；对串行模型残差0.983–1.992ms，条件性地加到重叠模型，得到每路33.1209–40.0273，即**33.1–40.0tok/s**。该区间是假设重叠后残差保持的模型情景，不是置信区间或逐层时间线实测。R045是短提示，不能把32K旧系数当同负载验证；T05逐层拷贝/计算/气泡仍待证据。

## 当前产物与缺口

`development/d10_staggered_20261009/`含冻结输入256版本、预测及CPU命令计划。已有计划器尚不实现CUDA错相位重叠，不可标原型完成，也不能据此测出重叠收益。实际原型需处理整步图契约、两路状态隔离、专家缓存槽归属、拷贝事件依赖，并按同两条AIPerf提示比较串行与错相位。

原128上限/ignore_eos=false负载保留；新增256/true负载单列。记录逐请求实际token、TTFT、TTFO、缓存、decode速率与每路门结果。正式GPU前复用既有准入/锁/独立审查，不制造新控制框架；不得先改发布运行路径。GPU及T16尚未执行。
''', encoding='utf-8')
    directive = ROOT / 'plan/ROOT_EXECUTION_DIRECTIVE_20261009.md'
    archive(directive)
    text = directive.read_text(encoding='utf-8')
    banner = '> 晚间有效更新见 [EVENING_DIRECTIVE_20261009.md](EVENING_DIRECTIVE_20261009.md)：D09/D10与Strata mini已批准，GPU按新队列；下文01:00内容保留为历史基础，冲突项以晚间更新为准。\n\n'
    if not text.startswith(banner):
        directive.write_text(banner + text, encoding='utf-8')
    readme = ROOT / 'README.md'
    archive(readme)
    text = readme.read_text(encoding='utf-8')
    banner = '''> **10-09晚间有效状态**：[新指令](plan/EVENING_DIRECTIVE_20261009.md)已归档，D09/D10与X-STRATA-R002-mini已批准；推送仍仅明早申请。独立481开发树已建，GPU按09:00观察→申请→R067d→R047/T03b→D09→D10排队。Strata v0.1.39无MTP服务被源码启动条件阻塞；不升级/构建/下载，未测。下方“Strata未批”等为历史状态。
>
> **论文v5.2**：[全文](paper/FreeToken_MultiGPU_CoExec_v5.2.html)仅更新§8的R045实测；C5等待mini。标题、多卡范围不变。[英文arXiv大纲](paper/ARXIV_ENGLISH_OUTLINE_20261009.md)已独审；尚未投稿。新CPU工装：[晚间文档/构建/渲染](development/evening_directive_20261009/)、[D10准备](development/d10_staggered_20261009/)、[D09预测证据](development/d09_prediction_20261009/)。开发与正式GPU门分别记录。

'''
    if banner not in text:
        readme.write_text(banner + text, encoding='utf-8')
    paperreadme = ROOT / 'paper/README.md'
    archive(paperreadme)
    text = paperreadme.read_text(encoding='utf-8')
    banner = '''> **当前v5.2（10-09晚）**：[HTML](FreeToken_MultiGPU_CoExec_v5.2.html)，11图20表，正文仅§8增加R045四请求22.03–22.53tok/s及串行模型对照，C5保持。用 `python paper/src/build_v52.py` 重建；v5.1源码/HTML/FTD原字节保留。[英文arXiv大纲](ARXIV_ENGLISH_OUTLINE_20261009.md)与v5.2独审见 [回执](../development/evening_directive_20261009/INDEPENDENT_PAPER_REVIEW.json)，桌面/手机见[渲染验证](../development/evening_directive_20261009/RENDER_CHECK.json)。以下v5.1表格为上一版记录。

'''
    if banner not in text:
        paperreadme.write_text(banner + text, encoding='utf-8')
    log = ROOT / 'plan/COORDINATION_LOG.md'
    with log.open('a', encoding='utf-8') as stream:
        stream.write(f'\n- {now} root：归档晚间六项用户决定；覆盖D09/D10旧卡并保留旧字节，481独立开发工作树已建，D10预测SHA {seal["sha256"]}已封存。D09逐轮消息边界仍在核对，尚未实现或验收；R002-mini已批但v0.1.39 serve要求MTP，源码门阻塞，零服务/零重试。v5.2仅§8及版本标记，英文大纲与独审/双视口渲染已完成。GPU未启动、推送未执行。R067d独立指令待定位。\n')
    (HERE / 'DOC_UPDATE_RECEIPT.json').write_text(json.dumps({'written_at': now, 'd10_prediction_sha256': seal['sha256'],
        'gpu_calls': 0, 'pushes': 0, 'prior_docs': str(HERE / 'prior_docs')}, indent=2) + '\n', encoding='utf-8')
    print(now, seal['sha256'])


if __name__ == '__main__':
    main()
