# D07 R024 原始文件分类的只追加更正

同类历史比较：R022/R025 在写入封存辅助源前固定原始文件集合；R024 的原登记额外包含 1 份收尾脚本。现用独立捕获的 73-file 基线补充分类，保留原 74 项字段及所有字节。

`E2-R024-gate-D07` 四臂测量及 manifest 字节验证通过。独立核查发现 `diagnostics.original_raw_files` 把 `source_tools/t16_r024_d04_close.py` 算成了测量原始文件；该文件有效且在 manifest 中，但属于收尾源。

通过 D04 追加 `diagnostics.raw_file_classification_correction`，id 为 `r024-raw-classification-20261004`。原字段、测量数值、原始文件、manifest 与 `kept` 均保持；没有删除或改写原记录。

- 原登记：74 项，包括收尾源 SHA `9b39ac514acf80ada54ebeb4ff7bd048667dc1f7f60f1bca93810e0cf86e384b`。
- 独立封存前测量基线：73 项；有序 `relative_path SHA256\n` 集合摘要 `0752924bb7a98f760d60ecac46403d66dd82d4116510d20ead393db7e001d358`。去除仅此一项后准确复现该摘要。
- 更正前 round SHA：`27c30ef5bfc2aa1e0cb5e4ecc8e2bbe78fbdbe60003609492f4477448a935ae4`。
- 更正后 round SHA：`d527648fdef34dc033df2202ab008ece74b2793fc10e38a09b9b92312c3e07eb`。
- manifest SHA 始终为 `54401ae6c0bca5709c01b46bfc14e84e3619ae1f01e6ce54ed79d4868199610f`；历史链与 manifest 再验均通过，全目录只读。

本地源及回执：`development/t16_r024_provenance_correction.py`、`t16_r024_provenance_review.json`、`t16_r024_provenance_correction_receipt.json`。服务器更正证据：`/data2/FreeToken/runs/dev_D07/r024_provenance_0752924/review.json`。

本更正只处理溯源分类。D07 默认 T16 通过不等于 T06 业务验收，不改变 D14/T17 或 E2-base.1 的接受状态。
