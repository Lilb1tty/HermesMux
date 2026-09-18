# 发布验收

发布前在锁定 Hermes Agent commit `c661785f872b5647fbac7c138d965180783bd9af` 上完成：

1. 设置 `HERMES_AGENT_SOURCE` 为该 checkout，运行 `python -m unittest discover -s tests -v`；不得跳过 Session 合约测试。
2. 在该 Hermes 环境执行 `hermes plugins doctor . --ci`，确认插件通过真实 manifest、导入和注册路径。
3. 对至少 200 条人工标注样本运行 `tools/evaluate_boundary_dataset.py`，退出码必须为 0。
4. 在真实个人微信账号中依次验证：普通消息、`新话题：…`、连续追问、自动切换、`撤销切换`、话题列表/切回、重启后切回、`session_search` 可找到旧会话。
5. 确认内置 `weixin` 已禁用，`weixin_topics` 已启用；两者绝不能使用同一 iLink token 同时轮询。
6. 发送 `话题统计`，确认检测失败时不切换，且延迟数据正常记录。
7. 记录回滚方案：停用 `weixin_topics` 后才启用内置 `weixin`；保留 `~/.hermes/state/weixin_topics.sqlite3` 备份。删除该数据库不会删除 Hermes Transcript，但会丢失话题索引。
