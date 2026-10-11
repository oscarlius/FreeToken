

## 2026-10-09T15:11:39.992127+08:00 条件部署准入

审批号 DEPLOY-E2-20261009-COND-01：release/cold两个实体扩展与gate字节相同，row_store移除且显式pinned路径CPU/源码证明不用；重编译资产仅归档。OPSv6.1 Linux/local48 passed 0 skipped，H2 PASS。按用户条件批准进入部署核验→serving→独占SDK/pytest冒烟；当前未放量。失败授权STOP-E2-20261009-COND-01和ROLLBACK-E2-20261009-COND-01，外来prefill exit75同版重测。push未批；R067c10/14和R0452/4仅在部署成功后、单独停服审批下执行；Strata未批。
