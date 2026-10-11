# 用户指令 2026-10-09 13:40（归档）

部署材料只改CPU代码与文档，不部署：H1显式smoke缺配置失败，回滚完整export，预期passed且skipped=0；H2只读归档rollback git ignored全空、184 ft serve help逐项argv、历史Prefill正则与usage；H3资源等待最大60秒并finally清自有锁/active，加CPU测试；M1health ok+serving；M2外来prefill判smoke_invalid，同版重启重测、不回滚；M3每分钟health日志/三次失败或supervisor退出告警文件；M4cwd=run_dir；LOW先signal再lock、环境diff。

R067已批准：RID E2-R067-d20-short-tail，P8192/8256×T1/30/63/64，最大6服务28调用。2个原样481热服务各seed donor0:P+1+4个不同tail查询，backend cached=P、新增=T，否则probe_invalid非产品失败。每P冷A/B各1服务D20构建cache关闭，逐query显式donor0:P+1→回退P→ordinaryP:P+T，cached0。生成/采样同T17，tokenIDs+全文对照，启动前证明D20diff只开发调度路径。8格全PASS才移除≤64待证及v5.1 C3勘误为尾段1–8193已证；A!=B failed_harness常设最多2工装重试；A=B但热diff not_met立即停/保留首分叉。

R045只CPU改481+AIPerf两路并发、去旧effb996/R040g依赖，给新范围，部署后排队。Strata22服务345调用未批准。
