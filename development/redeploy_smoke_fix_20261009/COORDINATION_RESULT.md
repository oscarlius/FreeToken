

## 2026-10-09T16:14:49.671237+08:00 重新部署481成功、独占结束

**重新部署成功，481d3a7已常驻serving并登记内网放量。** 审批 `DEPLOY-E2-20261009-REDEPLOY-01`：OPSv8 local/Linux FT venv各65 passed、0 skipped，独审PASS；旧184正常停止，release独占SDK+pytest冒烟1 passed、0 skipped、exit0。long行结构[512,7745]、正文SHA9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c及8257/128/8385完全符合预期，现场冷基准已签。首次通过、无invalid/retry/回滚；supervisor3015442/service3015453，GPU锁/实际身份已复核。未把冒烟称为业务任务或长期观察验收。R067c/R045尚未执行，每次停服另批；push和Strata未批。完整结果见[重新部署结果](../development/REDEPLOY_RESULT_20261009.md)。

现场首次冷基准SHA df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97；新发布证据manifest47ca9d497b30d4c0a0ee95789b8cd52651bceff03f833b04c7ca863d88eabed3。v7 BLOCK和v8 CPU65/0及两次独审PASS保留。当前生产GPU锁owner production:release:DEPLOY-E2-20261009-REDEPLOY-01。R067c→R045尚未取得停服审批，未执行；push/Strata未执行。
