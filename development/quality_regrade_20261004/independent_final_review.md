# 规范重判最终状态独立复核（2026-10-05）

同类历史比较：历史原始逐题判分38/60保留；规范39f判卷器对E0/R004/R009旧回答均重判47/60，180条状态和明细全部复现。
来源边界：当前可取的250e与39f也均重判47/60；历史内置grade_response的准确执行SHA缺失，不能把38→47归因这两个文件的差异。
接受边界：E2-R009-regrade的kept仅证明离线重判与来源一致，没有新生成、T17接受或E2-base.1接受。

复核者：独立verifier `d14_gate_review`，只读服务器CPU复算；根Agent另已读取当前规范文件和正式轮次哈希。

- 实际同步/封存使用冻结R2阶段 `/data2/FreeToken/runs/quality_close_e0d298834ba8`，13个源绑定和13项publication/bridge测试通过；旧e19阶段不作为实际执行证据。
- 同步journal保留flock、`renameat2(RENAME_NOREPLACE)`、旧文件备份、身份检查、实际读回和封存记录。
- 当前服务器判卷器SHA：`39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330`；客户端SHA：`bebedf0b74ab234620d7206d8da58b72565f78c7407f56a2055f98dd3e5bc62a`。
- E0数据库读回保留字面原值`0.7833`，只增加一条来源更正，注明47/60是旧回答离线重判，并保留历史38/60的执行来源缺口。
- 三份历史输入、三份逐题重判输出和全部41个manifest成员通过；D04追加检查通过，历史v001 pending、v002审核追加、v003 kept均保留。
- 当前round SHA：`7c18881bbd5d66d5ea66c2e4069da9c416f4c223381e4b01fe02218f735b8ec1`；原manifest SHA：`b7a88d869559ecca01fa24eab1113f15854ecf7be178649f7f0a19a6157cddb5`。

剩余溯源缺口：`finalize.py`没有包含在R2冻结来源或source/closure归档中，因此不能证明最终v002/v003追加驱动器的准确执行字节。实际追加效果、历史链和冻结D04写入器校验均已直接核实；此缺口不改写原工件或扩大kept的范围。
