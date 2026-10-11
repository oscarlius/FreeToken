# R067d CPU准备当前状态

实际归档：2026-10-09T20:31:28.158032+08:00。以[CURRENT_CPU_READY.json](CURRENT_CPU_READY.json)为准；旧PENDING和v2-v6回执为保留历史，不作为当前准入。

- 第1–4项CPU准备独审CPU_PASS；Linux FT venv：12 passed、10 subtests。
- 真实retry2/481/184运行日志七组正例与三类行反例、usage/POST边界、超额独立分支已回放。
- 保留完整冻结真实执行器，argv由固定配方构造并同函数算摘要；运行时在真实Popen之前执行≤120秒端口探测，失败先ss/lsof留证。
- FILEdry用真实执行器的两个函数，以fake probe/Popen完成10服务/14调用/20端口；请求传输是合成替身，没有真正服务、HTTP或GPU执行。
- [Linux回执](LINUX_CPU_RECEIPT_v7.json) / [独立审查](INDEPENDENT_CPU_REVIEW_v7.json) / [FILEdry回执](evidence_cpu_filedry_remote_v7/receipt.json)。

GPU未准入；真实child仍有root admission SHA占位。明早实际提交观察报告后再封存预检与准入，不用时钟过09:00代替。
