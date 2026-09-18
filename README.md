# HermesMux

HermesMux 是一个面向 **个人微信 Weixin iLink Bot** 的第三方 Hermes platform plugin。

微信里仍然只有一个私聊窗口，但插件会保守地判断你是否开启了新话题。每个话题都会通过 Hermes 官方 `SessionSource.thread_id` 进入独立 Session；切换话题不会清空或复制旧 Transcript，Hermes 的 Memory、压缩和历史检索仍照常工作。

> 当前版本已实现 Phase 2 检测代码，但尚未完成 200 条人工标注样本的 precision 门禁和真实个人微信 E2E。检测偏保守：不确定、超时或模型异常时一律留在当前话题。

## 安装

要求使用与本项目锁定接口兼容的 Hermes Agent。当前验证基线：

```text
NousResearch/hermes-agent@c661785f872b5647fbac7c138d965180783bd9af
```

先使用 Hermes 官方 Weixin 设置流程完成 iLink 二维码登录：

```bash
hermes gateway setup
```

然后安装并启用插件：

```bash
hermes plugins install Lilb1tty/HermesMux --enable
```

## 配置

在 Hermes 的 `config.yaml` 中启用 `weixin_topics`，并停用内置 `weixin`。两者不能同时轮询同一个 iLink token。

```yaml
platforms:
  weixin:
    enabled: false

  weixin_topics:
    enabled: true
    extra:
      account_id: "你的 iLink account_id"
      token: "你的 iLink token"
      base_url: "https://ilinkai.weixin.qq.com"
      cdn_base_url: "https://novac2c.cdn.weixin.qq.com/c2c"

      # 只允许配置过的管理员使用
      dm_policy: allowlist
      allow_from:
        - "你的微信 peer_id"

      # 插件只支持私聊
      group_policy: disabled
      text_batch_delay_seconds: 3.0
      text_batch_split_delay_seconds: 5.0

      topics:
        auto_detect: true
        confidence_threshold: 0.90
        detector_timeout_seconds: 3
        recent_user_messages: 4
        cooldown_turns: 4
        processed_retention_days: 7
        metrics_retention_days: 30
```

也可以继续使用 Hermes 官方的 `WEIXIN_ACCOUNT_ID`、`WEIXIN_TOKEN` 和 `WEIXIN_ALLOWED_USERS` 环境变量。配置完成后重启 gateway：

```bash
hermes gateway
```

## 使用

| 微信输入 | 结果 |
| --- | --- |
| `/new 讨论东京旅行` | 新建话题，并把“讨论东京旅行”作为新会话第一条消息 |
| `新话题：讨论邮件队列` | 同上 |
| `/new`、`新话题`、`换话题` | 新建空话题，下一条消息进入新会话 |
| `话题列表` | 查看最近话题和稳定短编号 |
| `当前话题` | 查看当前话题 |
| `切到 ab12cd34` | 恢复旧话题及其 Hermes 历史 |
| `撤销切换` | 返回上一个话题 |
| `归档当前话题` | 从默认列表隐藏当前话题，不删除 Transcript |
| `话题统计` | 查看自动换题次数、撤销反馈、检测失败数与 p95 延迟 |

自动检测默认静默运行：

- `换个完全不同的问题，东京怎么玩` 等明确换题表达会直接创建新 Topic；
- 没有提示词的换题会交给 Hermes 官方 `ctx.llm` 结构化判断，置信度达到 `0.90` 才切换；
- “继续”“刚才那个”“再解释一下”等延续表达不会触发切换；
- 新 Topic 前 4 轮为冷却期；模型超时、返回异常或低置信度时继续当前 Topic；
- 自动切错时发送 `撤销切换` 即可返回；触发消息仍完整保留在新 Topic 中。

检测器注册为 Hermes auxiliary task `weixin_topic_boundary`，复用 Hermes 已配置的模型与凭据，不需要在插件中填写新的 API Key。最近 4 条用户消息只保存在 gateway 进程内存中，每条最多 500 字；重启后清空并重新进入冷却期。

话题索引默认保存在：

```text
~/.hermes/state/weixin_topics.sqlite3
```

数据库只保存 Topic 元数据、当前指针和 7 天的 iLink 消息去重 ID，不保存检测上下文、完整聊天记录或 Hermes Session ID。自动检测还会保存最多 30 天的无内容指标（结果、置信度、延迟和撤销反馈），用于观察稳定性；撤销反馈不是人工标注 precision。

## 验证

```bash
python -m unittest discover -s tests -v
```

如要重新验证 Hermes 官方 Session seam，请把 `HERMES_AGENT_SOURCE` 指向目标 Hermes checkout 后运行同一命令。

发布自动检测前，按 [质量门禁](docs/QUALITY-GATE.md) 对至少 200 条人工标注样本运行离线评估；真实微信验收步骤见 [发布验收](docs/RELEASE-CHECKLIST.md)。

完整设计和后续自动检测门禁见 [技术规格书](docs/SPEC-weixin-multi-session.md)。
