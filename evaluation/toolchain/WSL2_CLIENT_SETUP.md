# WSL2 客户端说明（办公电脑访问 172.16.108.9）

本说明按 `plan/KIMI_RUNBOOK_PHASE2_20261011.md` 第 1.5 节编写，给办公电脑的 WSL2（Ubuntu）使用：复建评测客户端环境、访问服务器上的生产 / 测试服务，并明确三类测试的边界。本文档不改动服务器任何环境，不启动任何服务。

服务器：`dell@172.16.108.9`。生产服务监听 `172.16.108.9:8095`（局域网可达）；测试服务只在阶段 2 窗口内出现，监听服务器本机 `127.0.0.1:8123`。

## 1. 前置条件

- WSL2 Ubuntu（本机实测：python3 = 3.14.4，`python3 -m venv` 可用，pip 25.1.1）。
- ssh 客户端与免密密钥。本机做法：把 Windows 侧已有的密钥复制进 WSL2 并收紧权限（ssh 拒绝权限过宽的密钥）：

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cp /mnt/c/Users/liushangfeng/.ssh/id_ed25519 ~/.ssh/
chmod 600 ~/.ssh/id_ed25519
ssh dell@172.16.108.9 'echo SSH_OK'   # 首次会提示确认主机指纹
```

## 2. 复建 venv-aiperf 与 venv-eval

源文件（freeze 与 requirements）有两条获取途径，任选其一：

```bash
mkdir -p ~/freetoken-toolchain && cd ~/freetoken-toolchain
# 途径 A：从服务器复制（与服务器现行环境同一来源）
scp dell@172.16.108.9:/data2/FreeToken/evaluation/toolchain/{requirements-aiperf.txt,requirements-eval.txt,venv-aiperf.freeze.txt,venv-eval.freeze.txt} .
# 途径 B：从本机 Windows 工作区复制
cp "/mnt/d/00.开发/2026/03-模型实验/freetoken/freetoken/evaluation/toolchain/"{requirements-aiperf.txt,requirements-eval.txt,venv-aiperf.freeze.txt,venv-eval.freeze.txt} .
```

复建命令：

```bash
cd ~/freetoken-toolchain
python3 -m venv venv-aiperf
venv-aiperf/bin/pip install -r requirements-aiperf.txt
python3 -m venv venv-eval
venv-eval/bin/pip install -r requirements-eval.txt
```

说明与注意事项：

- `requirements-*.txt` 是钉死的直接依赖（aiperf==0.11.0；openai==2.54.0、pytest==9.1.1、lm-eval==0.4.13），让 pip 为本机 Python 重新解析传递依赖。
- `venv-*.freeze.txt` 是服务器上 Python 3.10.12 的精确传递锁定。WSL2 默认 python3.14，部分钉死版本可能没有 3.14 的预编译包；若 `-r venv-*.freeze.txt` 安装失败，改用上面的 `requirements-*.txt`，并在任何测试报告里注明客户端环境的实际版本差异。
- `lm-eval` 会拉入 torch，下载体积约 2 GB 级；工作时间请注意网络占用。
- WSL2 里这两个环境只用于 F / N 类测试（见第 5 节），不承担 S 类。

## 3. 版本检查（不发生成请求）

```bash
~/freetoken-toolchain/venv-aiperf/bin/aiperf --version
~/freetoken-toolchain/venv-eval/bin/python -c "import openai, pytest, lm_eval; print('openai', openai.__version__, '| pytest', pytest.__version__, '| lm-eval', lm_eval.__version__)"
```

参照值（2026-10-11 上午在服务器同名环境实测）：`aiperf 0.11.0`；`openai 2.54.0 | pytest 9.1.1 | lm-eval 0.4.13`。

## 4. 访问两个服务

### 4.1 生产服务（直连）

```bash
curl -s http://172.16.108.9:8095/health
```

- 8095 监听在局域网地址上，WSL2 直接访问即可（本机实测 TCP 连通）。
- `/health` 是状态查询；任何 `POST /v1/...` 生成请求都是测试行为，受第 5、6 节约束。

### 4.2 测试服务（ssh 隧道）

测试服务只监听服务器本机回环 `127.0.0.1:8123`，WSL2 必须走隧道：

```bash
ssh -L 18123:127.0.0.1:8123 -N -f dell@172.16.108.9
# 之后访问：
curl -s http://127.0.0.1:18123/health
```

- `-N -f`：不执行远端命令、转入后台。本地端口 18123 可换成其他空闲端口。
- 隧道连通性自检（服务未启动时也能做）：

```bash
# 正对照：转发服务器回环的 sshd，应读到 SSH 横幅
ssh -L 10022:127.0.0.1:22 -N -f dell@172.16.108.9
timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/10022 && head -c 30 <&3'; echo
# 期望输出类似：SSH-2.0-OpenSSH_8.9p1 Ubuntu-3
```

- 阶段 2 之外 8123 上没有进程监听：此时 `curl 127.0.0.1:18123/` 得到 "Connection reset / Empty reply" 属正常，说明隧道通路本身正常（本机实测如此）；服务起来后才会返回内容。
- 用完关闭：`pkill -f "[1]8123:127.0.0.1"`（正对照隧道同理换成 10022）。

## 5. S / F / N 三类测试边界

| 类别 | 含义 | WSL2 可以做吗 |
|---|---|---|
| S | 服务器本机性能基线 | **不可以**。只在服务器本机测，WSL2 的结果不得混入 S 数据 |
| F | 功能与质量 | 可以 |
| N | 局域网体验 | 可以，但**必须单独建立 N 类基线**，不得与 S 类数据混用或对比 |

## 6. 禁止事项

- 服务器本机做测速（S 类或阶段 2 窗口）期间，**禁止从 WSL2 并发发送任何请求**（包括 `/health` 之外的任何生成请求）；窗口时间以协调日志 `plan/COORDINATION_LOG.md` 的告知为准。
- 观察窗口内（协调日志另行告知）不对生产服务发任何生成请求。
- 不修改服务器上的任何环境与服务；隧道只读转发。

## 7. 本文档命令的验证记录（2026-10-11 上午，阶段 1）

- 服务器侧版本检查：`aiperf 0.11.0`；`openai 2.54.0 | pytest 9.1.1 | lm-eval 0.4.13`；服务器 venv 的 python 为 3.10.12。
- WSL2 侧：`python3 -m venv` 建/删演练通过（pip 25.1.1，python 3.14.4）；`ping 172.16.108.9` 与 TCP 8095 直连通过。
- WSL2→服务器 ssh：密钥复制 + `ssh dell@172.16.108.9 'echo SSH_OK'` 通过（返回 `SSH_OK` / `dell`）。
- 隧道：`ssh -L 10022:127.0.0.1:22` 正对照读到 `SSH-2.0-OpenSSH_8.9p1 Ubuntu-3`；`ssh -L 18123:127.0.0.1:8123` 在服务未启动时 curl 收到 connection reset（符合预期，通路正常）。验证后隧道进程已清理。
- 未在本机实际执行完整 pip 安装（避免工作时间大体积下载）；安装命令与服务器已验证环境同源，freeze/requirements 文件两侧一致。
