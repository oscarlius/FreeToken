# 晚间执行准备与论文增量

任务依据：`plan/EVENING_DIRECTIVE_20261009.md`。所有协调记录由执行时实际UTC+08时间生成；不把计划时间写成完成时间。

- `prepare_paper.py`：从保留的v5.1正文生成仅§8+版本标记修改的v5.2，检查旧源码/HTML/FTD字节未变；重建命令为 `python paper/src/build_v52.py`。
- `render_paper.py`：本地浏览器验证桌面和手机布局、内部锚点、数学及§8实测文字。
- `read_t2_sources.py`：SSH/SFTP只读既有T2轨迹和回放，下载到D09证据目录并逐件SHA绑定；不发送模型请求。
- `update_execution_docs.py`：归档旧卡原字节并更新晚间范围、D10预测封存、README及真实时间协调日志。它是本次一次性迁移工具；重跑会覆盖卡面后续追加，交付后不要重跑。
- `observation_snapshot.py`：读取既有观察记录与/proc，不发送HTTP、启动服务或操作GPU。

独立论文审查见 `INDEPENDENT_PAPER_REVIEW.json`，范围检查见 `PAPER_SCOPE_CHECK.json`，渲染见 `RENDER_CHECK.json`。这些文件不代表D09/D10 GPU验收或arXiv投稿。

Strata文件和源码审计严格位于兄弟 `strata/` 目录；本目录不包含Strata启动/测试脚本。
