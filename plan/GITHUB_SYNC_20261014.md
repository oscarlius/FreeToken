# 收尾代码同步到 GitHub

用户在本地收尾后明确授权：“ok，代码提交到 github”。该授权覆盖此前仅本地收尾的“不推送”限制，范围为已收尾的代码与研究记录；不新增 PR、不改变部署、不发布独立论文审核仓库或本地大归档。

远端已核对为用户本人可写的公开 fork：`oscarlius/FreeToken`，上游为 `FlashML-org/FreeToken`。

| 远端分支 | 本地来源 | 提交 |
|---|---|---|
| `main` | 研究仓库 `main` | `9c48527` 收尾提交及本次同步说明 |
| `release/e3` | `product/` 的 `release/e3` | `9db0ee776c25afa8d2719ab700b2de7ccc606142` |
| `release/e2` | `product/` 的 `release/e2` | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` |
| `integration/final-20261014` | `upstream-flashml/` 的 `main` | `a7c24b27612769ff25929c39c7cf65ded34aeccc` |

执行只使用普通快进或新增分支推送；不强推、不删除远端分支、不推送归档标签。源码内容与本地验收版本一致，无需重复 GPU 测试。

同步前检查：工作区干净；两个源码树及本次新记录未发现常见令牌或私钥格式；待推送路径无模型权重和本地归档。同步后用 GitHub 远端 refs 核对每个分支的完整提交号。
