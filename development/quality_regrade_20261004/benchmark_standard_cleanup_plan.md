# benchmark_client 判卷收敛计划

范围只限 `../_shared/benchmark_client.py` 的 phase3 判卷路径。

1. 删除内联的分类判卷实现，保留 `grade_response` 的 `(bool, detail)` 调用契约。
2. 只从同目录 `evaluator.py` 加载固定 SHA-256 `39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330` 的 `grade_question`；哈希、导入或判卷器错误立即失败，不把错误计作模型分数。
3. phase3 每个响应只调用一次标准判卷，并在返回汇总和每条 JSONL 记录中写入判卷状态及 evaluator、client、corpus SHA-256。
4. 不改生成请求、`max_tokens=768`、API、计时字段或非判卷统计。

回归测试以 AST 提取判卷函数并替换 `call_chat_stream`，不导入 tokenizer、不访问 API 或 GPU。它覆盖内容与思考分离、每题单次判卷、错误判卷器拒绝、溯源字段和既有统计字段保留。
