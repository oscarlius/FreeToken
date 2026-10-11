# 办公机 WSL2 部署 FreeToken（RTX 3090 涡轮 24GB / 64GB RAM）

> 2026-10-06。目标：在办公机（i7-12700KF，64GB，RTX 3090 涡轮 24GB，Win10 LTSC 19044）的 WSL2 里跑通 FreeToken E2-base.1。
> **角色定位：开发/演示/验收节点**——不是生产，不是正式性能测量点（办公 OS 干扰源多，数字须标注"桌面节点"）。
> 对照的服务器基准：RTX 4090 + 251GB RAM，冷 32K TTFT 6.44s / 解码 38.5 tok/s（T20 PRODUCTION 实测）。

## 0. 预期与三个未验证点（诚实标注）

**预期**：解码 35–38 tok/s（专家流 PCIe/内存带宽主导，3090 平台喂得动；HBM 936 vs 1008 GB/s）；冷 32K TTFT **12–14s**（预填算力约为 4090 的四成，这项必然明显慢）。

**未验证、首跑要盯的**：
1. 47.7GB 大块锁页（`cudaHostAlloc`）在 WSL2 虚拟机里的提交行为；
2. 启动脚本（bash + taskset）在 WSL2 的兼容性（应兼容，CPU 编号映射不同）；
3. sm_86 首次 JIT 编译（FT 内核用 torch cpp_extension 按本机 GPU 自动编译，无需改代码，首次启动多等几分钟）。

## 1. 硬件与 BIOS

- **内存升到 64GB 是硬前提**（当前 31.8GB 放不下 47.7GB PLE）；确认双通道。
- 3090 涡轮是单槽 blower：注意机箱风道（GDDR6X，~350W）。
- BIOS：**Above 4G Decoding 开**；Resizable BAR 建议（非必须）。

## 2. Windows 侧

```powershell
# 1) NVIDIA 驱动装 Windows 侧最新版（WSL2 CUDA 需 R470+）；WSL2 内不要装 Linux 驱动
# 2) WSL2 就绪
wsl --update
wsl --set-default-version 2
wsl --install -d Ubuntu-22.04
```

`C:\Users\liushangfeng\.wslconfig`（64GB 物理留 8GB 给 Windows）：

```ini
[wsl2]
memory=56GB
processors=16
swap=8GB
autoMemoryReclaim=disabled
```

`wsl --shutdown` 后重开；`wsl` 内 `free -g` 应显示 ~54–56GB。**这一步不做，47.7GB 锁页必然失败。**

## 3. WSL2 内环境（对齐服务器：Python 3.10.12 / torch 2.11.0+cu130 / gcc 11.4 / CUDA 13.0）

```bash
sudo apt install -y build-essential gcc-11 g++-11 python3.10 python3.10-venv
# CUDA Toolkit 13.0：只装 toolkit 拿 nvcc（不装 Linux 驱动，libcuda 由 /usr/lib/wsl/lib 注入）
python3.10 -m venv ~/ft-venv && source ~/ft-venv/bin/activate
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu130
```

验证三连：

```bash
nvidia-smi                                            # WSL2 内应能看到 3090
python -c "import torch; print(torch.cuda.get_device_capability())"   # 应输出 (8, 6)
nvcc --version                                        # 必须 13.0（FT 的 check_nvcc_matches_torch 会核对）
```

## 4. 代码与模型落位（关键：别放 /mnt/g）

引擎和模型都放 **WSL2 的 ext4**（`/mnt/g` 走 9p 协议，随机读和锁页性能极差）。G 盘（Seagate 1TB SSD，720GB 空闲）以 vhdx 形式承载 ext4，兼顾空间与 IO：

```powershell
wsl --import FT G:\wsl\FT-ext4.vhdx <已安装的Ubuntu-22.04的tar或直接用--export/--import迁移>
```

（若不想迁移，退一步：Ubuntu 装在 C/D 盘也行，只要模型放在 WSL ext4 内且 vhdx 所在物理盘有 ≥150GB 空闲。）

```bash
# 代码（内网直连服务器）
rsync -avP --exclude venv --exclude __pycache__ \
  dell@172.16.108.9:/data2/FreeToken/wt/e2base1/ ~/ft/e2base1/
# 模型（~124GB，走内网全速；SSD 上冷加载远快于服务器机械阵列）
rsync -avP dell@172.16.108.9:/data2/model/Qwen3.8-Flash-Next-NVFP4/ ~/models/Qwen3.8-Flash-Next-NVFP4/
```

（等 T20 封存后以 `release/e2` 分支为准替换 e2base1 工作树。）

## 5. 启动与冒烟

照生产口径启动（层优先、窗口 73728、端口 8095），**改动两点**：

1. 去掉 `taskset -c 1,3-47`（WSL2 CPU 编号映射不同；要绑就 `-c 4-19` 避开中断核，先不绑跑通再说）；
2. 首次启动会 JIT 编 sm_86 内核（几分钟，一次；缓存在 `~/.cache/torch_extensions`），PLE 47.7GB 首次 `cudaHostAlloc` 物理页提交也慢——**首次启动预留 20–30 分钟属正常**。

冒烟顺序（照 00_规则口径，数字标注"桌面节点"）：

| 步 | 内容 | 通过线 |
|---|---|---|
| 1 | `GET /health`、`GET /v1/stats` | 200、模型名正确 |
| 2 | 冷 32K TTFT ×1（首枪单列） | 记录数字即可（预期 12–14s） |
| 3 | 短上下文解码 ×3 | 预期 35–38 tok/s |
| 4 | 60 题抽 5 题 + 规范判卷器 | 判卷通过 |

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `cudaHostAlloc 47.7GB` 失败 | 确认 `.wslconfig` memory=56GB 已生效；仍失败 → 降 KV 窗口（如 32768）或 PLE 分块锁页 |
| WSL2 内存回收挤压锁页 | `autoMemoryReclaim=disabled`；跑引擎时别休眠 |
| Win10 LTSC 的 WSL2 内核旧 | `wsl --update` 到最新 |
| 办公软件干扰测量 | 跑数字时关浏览器/杀毒实时扫描 |
| 凭据安全 | SSH 密码走环境变量，不写文件不进日志（与 §8.8 WP-R 同规） |

## 7. 验收对照表（首跑后填）

| 指标 | 服务器 4090（T20 PRODUCTION） | 办公机 3090 实测 | 备注 |
|---|---|---|---|
| 冷 32K TTFT | 6.44 s | ___ | 预期 12–14s，算力差 |
| 解码 tok/s | 38.5 | ___ | 预期 35–38 |
| 短上下文 tok/s | ___ | ___ | |
| PLE 锁页 | 47.7 GB | ___ | WSL2 首跑重点观察 |
| 60 题抽 5 题 | — | ___ | 规范判卷器 |

## 8. 明确不做的事

- 不当生产服务（单实例、无冗余、办公网络）；
- 不把桌面节点的数字混进服务器轮次对比（论文引用须标注硬件）；
- 不在 WSL2 里装 Linux NVIDIA 驱动（会破坏直通）。
