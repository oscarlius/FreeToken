# FreeToken 研究仓库

本 fork 保存 FreeToken 的研究材料、论文与实验记录。GitHub `main` 是研究仓库入口，不对应运行产品源码。

## 产品与代码分支

| 用途 | 分支与提交 | 说明 |
| --- | --- | --- |
| 已部署产品源码 | [release/e3](https://github.com/oscarlius/FreeToken/tree/release/e3) · `9db0ee776c25afa8d2719ab700b2de7ccc606142` | 当前产品的精确源码版本 |
| 产品回退点 | [release/e2](https://github.com/oscarlius/FreeToken/tree/release/e2) · `481d3a7` | 保留的源码回退版本 |
| 已合并贡献 | [integration/final-20261014](https://github.com/oscarlius/FreeToken/tree/integration/final-20261014) · `a7c24b2` | 合并 #686 与 #688 的代码，尚未部署，未完成合并版本的 GPU 联合验收 |

克隆产品源码：

```bash
git clone --branch release/e3 --single-branch https://github.com/oscarlius/FreeToken.git FreeToken-product
```

## 研究与论文

- [论文目录](paper/README.md)：版本、证据边界与重建说明。
- [论文正文 v5.8](paper/FreeToken_MultiGPU_CoExec_v5.8.html)：本地 HTML 文件。
- [研究计划与记录](plan/README.md)：实验与资料入口。
- [评测工具链](evaluation/toolchain/README.md)：评测环境和工具说明。

## 收尾记录

产品分支、合并版本、清理范围与验证证据见[本地收尾报告](development/local_finalization_20261014/FINAL_STATE.md)。

[服务器收尾结果](development/server_finalization_20261014/RESULT.md) · [凭据检查](development/server_finalization_20261014/SECRET_AUDIT.md)

此前首页的完整历史内容已原样归档至
[README_BEFORE_20261014.md](development/server_finalization_20261014/README_BEFORE_20261014.md)。

运维脚本通过 `FT_SSH_HOST`、`FT_SSH_USER` 和可选的 `FT_SSH_PASSWORD` 环境变量连接；不设置密码时使用 SSH 密钥或 agent。
