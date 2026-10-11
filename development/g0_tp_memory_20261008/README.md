# G0 只读复核附件

本目录仅保留 2026-10-08 T12-S-002 证据复核的最小附件。远端读取通过现有 SSH 认证完成：只读取 safetensors 文件头和既有服务日志；未读取 tensor body，未启动服务，未操作 GPU 或端口。

可复核的历史日志身份记录在 `plan/data_releases/FTD-20261003-1.SERVER_HASHES.sha256`；结论和完整缺口见 `plan/01_测试与调研/results/T12-S-002_20261008.md`。
