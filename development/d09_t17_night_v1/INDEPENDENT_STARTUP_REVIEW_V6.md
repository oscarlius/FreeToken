# T17 v6 最终独立启动复审

## Code Review Summary

**Files Reviewed:** 4  
**Total Issues:** 0

### By Severity

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 0

### Evidence

`d09_t17_runner_v6.py` 的本地和远端 SHA 均为 `1f9bca11c8005dbf5de4d92223b01a5fbdb4630f7defb183129907ada052ee5e`。不再通过错误文本推断清理状态：实际和 fake 路径都将回绑异常包装为 `PostCleanupRebindFailure`。该异常使 child 保留 D07 task lock、以非零退出、写入 `unsafe_cleanup.json`（`failed_harness`、`post_cleanup_closed: false`），且不写 closed terminal。

本地 AST 解析通过；`test_d09_t17_runner_v6.py` 为 2 passed，其中失败测试注入实际 `OSError(98, 'Address already in use')` 并验证锁保留、unsafe receipt 和 terminal 缺失。远端 CPU FILEdry v14 terminal SHA 为 `a1e1755fe0b393790f07bf53da5c271f33dfc1a4cb661d59fbad1196c6de99dc`：sealed T16、controller/child、atomic receipt、6 services、8 calls 和成功回绑终态均存在。该 CPU 结果的 `product_acceptance` 仍为 false。

### Historical review integrity

未发现被覆盖的原 V5 独立拒收收据备份。现存 `INDEPENDENT_STARTUP_REVIEW_V5.json` SHA 为 `c15993efd261fcea99d69418ee04352165d13dc01d0460c871dc9ad1589c5745`、MD SHA 为 `1551dd2320b7150789014e2deeb97cdb20a1584860a9a44124c5b74033ab178b`；其内容是作者 handoff，不能作为独立审查。V6 收据保留该覆盖风险，但无法恢复原字节。

### Recommendation

**APPROVE startup remediation.** Root 仍须在独立 T16 closure 存在后签发正式 root admission；本审查未启动 GPU、HTTP、服务或编译。
