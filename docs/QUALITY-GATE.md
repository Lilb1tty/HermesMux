# 自动换题质量门禁

自动检测只能在至少 200 条人工标注的中文连续/换题样本上通过以下门槛后默认开启：

- precision ≥ 95%；
- 明显换题 recall ≥ 60%；
- `timeout`、`error` 或其他非 `ok` 的模型结果不得切换。

标注文件为 JSONL，每行只包含稳定案例编号和人工结论：

```json
{"id":"case-001","is_new_topic":true}
```

模型预测文件使用同一组编号：

```json
{"id":"case-001","is_new_topic":true,"confidence":0.97,"status":"ok"}
```

运行：

```bash
python tools/evaluate_boundary_dataset.py --labels labels.jsonl --predictions predictions.jsonl
```

退出码 0 代表全部门槛通过。样本内容不提交到本仓库，避免把私人微信文本写入版本控制。
