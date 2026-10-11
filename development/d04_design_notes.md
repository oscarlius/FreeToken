# D04 候选实现与验证记录（尚未正式发布）

D04候选已实现并完成服务器隔离验证，已用于T10及T08 P1/P2真实轮次收尾。追加/关闭工具已发布到正式scripts并更新01收尾流程；比较脚本仍为原版本，待基线测试及D03门禁结束后同步。

## 当前候选验证

- 服务器隔离目录：`/data2/FreeToken/runs/dev_D04/candidate`；10文件包SHA256 `6bb1e69111812367b2accab7b5f3075d9592f904d53d55b740fae4ea735b4b77`，本地/远端/清单逐项一致。
- 服务器专项18/18 PASS，包括Linux符号链接、只读权限回滚、历史列表截短拒绝、retraction目标校验、关闭器及标签；独立复核PASS。
- G2：合成轮次close→verdict→retract→check有效，原manifest字节保持不变。
- G3：真实B→B2的12行、B→A的11行逐长度旧输出字节一致；仅结论标签更正。B→B2不称恢复；B→A根据真实resume标注恢复。
- 真实轮次验收：E2-R006/batch34独立复核PASS后，归档三份D04工具及版本，以新 `round_close.sh` 封存；新写入器check、manifest、只读权限、v001字节一致全部通过。MANIFEST SHA256 `9c70ea49c1daf40f5851f246fa8b6e44927a3d00a1962a8a51b74ab36613619b`；版本清单SHA256 `ce8d2196d5a738ff435287c50300ef2f63e832417aaeba30bfabac93dce36f6f`。
- 新round工具已发布到 `/data2/FreeToken/scripts/`，与本地MD5一致：writer `88178a9a3c83dec204e90e6dcf8c4db9`，close.py `415aa82b34c8fd82d09bfe8a8ce67eed`，close.sh `430693122ef66bb5a293fb421ff0f7fc`。正式版本对E2-R006执行check通过。发布记录 `runs/dev_D04/publish_new_round_tools_20261004.json` SHA256 `5b072b95b43e362cdda984bebba9c6c5efc5669ae6133f93d33231b9d1ab900a`。
- 真实关闭后追加：E2-R006通过正式writer add新增服务端缓存诊断，形成v002，当前round SHA256 `b3e306df41b3da849e9a796646cf2fad18b17dc869cb2a300a79e82d9b10706e`。原v001和测量保持不变，manifest不变，历史链及全目录只读校验通过；正式判定仍pending_review。
- T08 P1真实收尾：E2-R009/batch36独立复核PASS后通过D04封存；MANIFEST SHA256 `d0b8ef2a7597c438fb0cda68fd89d30d287280b6f9c965d7ef95007cf68c4fca`。随后用writer add补三趟Agent各12请求的整趟汇总，形成v002，当前round SHA256 `14db9695f825ff7691aef0da0e9c5b9286bce98ac745a3a16bdc423126f4c6fd`。原v001、已有字段及manifest保持不变，历史链与只读校验通过。
- T08 P2真实收尾：E2-R009-p64k/batch37独立复核PASS后通过D04封存；MANIFEST SHA256 `a329ddbacb15728507070010e13c942e44951b39156e5e69ceb7a895a5e5ae2f`，round/v001 SHA256 `b3ee44b5941b5dbba0470e315d00cfa39a5c111c8002a3900af6dd2b68135b70`。父轮次五份源文件绑定不变，两轮正式判定仍pending_review。
- 未覆盖正式比较脚本，未修改任何已关闭历史轮次，未执行正式判定追加；比较标签发布完成前不标D04全部交付完成。

## 实际源码版本

- 服务器 `/data2/FreeToken/scripts/agent_trace.py` MD5 `f81acb79c3dbc89999f5f76de4c9a070`；本地旧版 MD5 `eec0806b9fbc021ef7dcae37447d9172`。
- 已从服务器获取小源码到 `development/d04_agent_trace_remote.py`，保留本地旧版。实际diff为16行新增、2行删除：增加 `generate --seed-file`；限制文件在root下；内联原文最多120000字符；输出实际task_prompt、seed_file、seed_chars。D04以远端版为合并基点，保留此功能。
- state_eq MD5 `0019f904d8d2578dd507ba40b149d7eb`；serve_args_diff MD5 `ce123cb0af201d99baac91f7f8e4f8c7`，本地/服务器相同。
- 服务器正式scripts现已有 `round_json_append.py` / `round_close.py` / `round_close.sh`。此前使用的initial_measurement_close只做首次关闭，不是D04追加工具；T10只复用它的初始工件校验，实际关闭使用D04工具。

## 写入器与关闭器

- 新增 verdict/retract/add/check CLI；当前round字节必须等于最新history快照。递归保留所有既有值及列表前缀，类型也须保留，特别是bool不能等同int。
- 唯一既有值变更：带匹配历史记录的top-level verdict，以及带真实retraction或对应理由的子结论status。其他删键、改数字、改列表中部、无对应记录改判定均拒绝。
- 变更前完整校验历史链、JSON路径、必填理由/证据/角色、属主和路径。失败不写轮次文件；成功新增快照与SHA256SUMS后恢复只读，并处理发布/权限失败回滚。
- legacy v000必须与历史原文件逐字节相同；legacy_snapshot用旁注，不往快照JSON增字段。check只读。
- close检查round、batch.sh和每个声明臂的四个必需文件；生成初始快照、manifest、只读权限并打印manifest自身SHA。manifest排除round.json、round_history及自身；后续追加不重算manifest。

## 比较标签与验证

- 标签默认取真实路径最后两级，可显式覆盖。state_eq仅test侧实际含resume时称“恢复”；保持逐长度旧输出与返回码。
- 同步agent_trace compare与serve_args_diff的人类可读标签，保留现有parse及JSON字段/返回码。
- G1：合法追加；拒绝旧数值、删键、列表中间改写、类型变化、判定/历史不符、历史字节或哈希漂移。
- G2：/tmp合成轮次close→verdict→retract→check，历史链有效、原manifest字节不变。
- G3：真实dump_B→dump_B2不称bank恢复，dump_B→dump_A按实际resume标恢复，逐长度输出与旧版逐字相同。
- README登记脚本及停止使用rev_*.py；交付本地/服务器MD5相同，并以新工具收尾下一正式轮次。历史日志不改。
