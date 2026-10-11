# T19　Strata 本机基线（同一模型，GGUF）

> 执行者：低成本模型。占 GPU，**只在主线 GPU 队列的空档执行，不得抢占**。轮次 ID：**X-STRATA-R001**（其他框架的 GPU 轮次，规则见 `00_规则` §10.9）。依据：`../PLAN_20261005_重新规划.md` §0、§5；`../../research/REVIEW_STRATA_REUSE_20261005.md` 第 2 节。
> 目的有三：给论文一个同模型、同硬件的对比基线；验证 Strata「CPU 原地计算未命中」的路线在本机（双路 DDR4、无 AMX）下的实际速度；给业务一个备选参照。

## 0. 约束

- 代码目录按 AGENTS.md 放在仓库根目录下的 **`strata\`**（即 `D:\00.开发\2026\03-模型实验\freetoken\strata\`），远端 `/data2/Strata/`（新建），不放 `_shared/`。按 AGENTS.md 第 3 条，在 `strata\README.md` 记录本次安装、启动命令与版本。版本固定为 `6f32ec0`：`git -C strata/Strata checkout 6f32ec0`，远端同样检出该提交，记录 `git rev-parse HEAD`。
- 模型权重放 `/data2/model/<名称>/`，用软链接接入，不重复拷贝。下载在工作时间（08:00–17:30）限速 4.5 MB/s（`--max-overall-download-limit=4608K`），17:30 之后可以全速。
- 不改 Strata 源码。所有命令、版本、配置（`strata-*.json`）原样保存。
- 与 FreeToken 服务互斥：开始前确认 GPU 空闲、无锁；运行期间持有共享锁 `/data2/_shared/gpu.lock`，结束后释放。

## 1. 前置

- **端口用 8085**：服务器 8080 被 Open WebUI 的 docker 容器占用（生产设施，不动），偏差已记入 `strata\README.md`。
- **现成脚本，照原样执行**：`strata\run_t19_all.sh`（安装与总流程）、`strata\batchX_STRATA_R001.sh`（单写者门、GPU 锁、各测量项）、`strata\two_way_client.py`（两路）、`strata\judge_t19_offline.py`（离线判分）。下文命令只用于核对脚本内容，不另写脚本。

- 卡D18（客户端参数化）已交付；否则停止，不得修改客户端。
- Strata 服务启动命令（照 Strata 文档）：`python -m serve.server --engine strata --config strata-<model>.json --port 8085`。模型名从 `GET /v1/models` 读取，记录到结果文件。
- 客户端：卡D18 已交付并同步到 `/data2/FreeToken/scripts/`，先核对 `probe_ft_cold32k.py` 的 md5 为 `a027c1aa8a0b85d6bb94ce9860d7fa66`。以下命令可直接粘贴，`$M` 为 `GET /v1/models` 返回的模型名：
  - 探针的 `OUT_DIR` 写死在 FreeToken 目录（`/data2/FreeToken/runs/cold32k_20261002/`）；Strata 的结果以 stdout 重定向文件为准，存入 `X-STRATA-R001` 目录。
  - 冷 32K：`python3 probe_ft_cold32k.py xs-cold32-<i> 32052 128 nothink --url http://127.0.0.1:8085/v1/chat/completions --model $M`。冷 64K 把 32052 换成 65412。`cold_id` 每次不同（换前缀）。
  - 两路：用 `strata\two_way_client.py`（两路不同内容、每路 512 token，记录各自起止时间）。**不用** `multisession_probe.py`（它依赖 FreeToken 的暂停端点）。
  - 60 题：`FT_API_BASE=http://127.0.0.1:8085/v1 FT_MODEL_NAME=$M FT_RUN_DIR=$O/quality60 python3 /data2/_shared/benchmark_client.py phase3 $M /data2/_shared/test_prompts_60.json`。现版客户端会内联调用经 SHA 校验的规范判卷器，`quality_results_*.jsonl` 中的 `graded_status` 与 `evaluator_sha256` 可直接采用；`judge_t19_offline.py` 只作复核，两者不一致即停止上报。
- 冻结开关写在 `strata-<model>.json` 的 `"args"` 数组里（格式见 Strata `docs/BATCHING.md`）；两路项另存一份配置，加 `"parallel": 2`。所有配置原样存入轮次目录。
- `01_测试与调研/README.md` 的批次模板写死了 8095 端口和 FreeToken 工作树断言。T19 不套用该模板：保留单写者门与 GPU 锁两段，端口改 8085，工作树断言换成 `git -C /data2/Strata/Strata rev-parse HEAD` 以 `6f32ec0` 开头。

## 2. 安装

1. 按 Strata `docs/INSTALL.md` 的 Linux 路径构建 CUDA 后端：`./setup.sh --model IQ3_S --context 131072 --vision no --yes --port 8085 --data-dir /data2/Strata-data --gguf-dir /data2/model/Qwen3.8-Flash-Next-IQ3_S-GGUF --no-browser`。**`--context` 必须是 131072**：32768 放不下冷 64K（65412 + 128）。`strata\README.md` 中的 32768 以本卡为准。记录编译器、CUDA 与驱动版本，以及构建日志的 sha。
2. 模型档位：**IQ3_S**（官方推荐的最高质量 2–3 bit 档）为主；如时间允许，再测 Q2_0。来源按 Strata `docs/MODELS.md`，记录文件 sha256。
3. 冻结自适应，保证可复现（写入配置的 `"args"`）：`--adapt-every 100000 --prompt-cache 0 --adapt-swaps 0 --pcie-frac 0`。另设一个「默认配置」臂，只作参考。

## 3. 测量（与我们的套件同口径）

| 项 | 内容 | 次数 |
|---|---|---|
| 1 | 冷 32K 首 token 与解码 128 token（换前缀），命令见第 1 节 | 4，首枪单独记录 |
| 2 | 冷 64K | 2 |
| 3 | 短上下文解码 | 3 |
| 4 | 两路不同内容同时解码（Strata `"parallel": 2`），每路 512 token，命令见第 1 节 | 2 |
| 5 | 60 题，规范判卷器 `evaluator.py`（sha256:39f10fa8…），同一题库；记录 `max_tokens` 与思考设置，与 FreeToken 的 T20 第 6 项配置相同 | 1 |
| 6 | NUMA 对照：`numactl --interleave=all` 对 `numactl --cpunodebind=1 --membind=1`（node1 能放下的前提下） | 第 1、3 项各 2 次 |

## 4. 报告（不作为 FreeToken 的验收）

- 结果写 `results/T19-X-STRATA-R001_<YYYYMMDD>.md`。开头 3 行写：解码 / 首 token / 60 题三组数字，与 FreeToken E2-base（T00、E2-R009，规范判卷器重判 47/60）的并列比较。
- **必须写明量化位数不同**（Strata 2–3 bit GGUF，FreeToken NVFP4 约 4.5 bit），速度与质量必须同时报告，不能只报速度。
- 记录 CPU 线程数、实际绑核、内存占用、PCIe 份额（`--pcie-frac`）。

## 5. 停止条件

构建失败、模型下载失败或磁盘余量不足（先 `df -h /data2`；IQ3_S 约 70–80 GB，Q2_0 另需约 40 GB，余量低于「所需 + 50 GB」不下载）；`setup.sh` 要求 sudo 或安装系统级 CUDA/驱动（不得执行，停止上报）；node1 空闲内存（`numactl -H`）小于模型文件 + 20 GB 时跳过第 6 项的 membind 臂、GPU 被主线需要：停止并上报，不自行修复 Strata 源码。
