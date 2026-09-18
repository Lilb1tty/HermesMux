# HermesMux

HermesMux 是一个面向 **个人微信 Weixin iLink Bot** 的第三方 Hermes platform plugin。

微信里仍然只有一个私聊窗口，但你可以在这个窗口里创建多个逻辑话题。每个话题都会通过 Hermes 官方 `SessionSource.thread_id` 进入独立 Session；切换话题不会清空或复制旧 Transcript，Hermes 的 Memory、压缩和历史检索仍照常工作。

> 当前版本是 Phase 1：支持显式创建和切换话题。自动识别“用户是否换了话题”尚未启用，避免未经评估的误切换污染会话。

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
        processed_retention_days: 7
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

话题索引默认保存在：

```text
~/.hermes/state/weixin_topics.sqlite3
```

数据库只保存 Topic 元数据、当前指针和 7 天的 iLink 消息去重 ID，不保存完整聊天记录或 Hermes Session ID。

## 验证

```bash
python -m unittest discover -s tests -v
```

如要重新验证 Hermes 官方 Session seam，请把 `HERMES_AGENT_SOURCE` 指向目标 Hermes checkout 后运行同一命令。

完整设计和后续自动检测门禁见 [技术规格书](docs/SPEC-weixin-multi-session.md)。
