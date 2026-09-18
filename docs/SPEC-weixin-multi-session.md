# Weixin 个人微信多话题会话插件 — 技术规格书

| 字段 | 值 |
| --- | --- |
| 文档版本 | v1.1 |
| 作者 | Owen Zou（邹博文）+ Hermes |
| 修订日期 | 2026-09-18 |
| 状态 | Phase 2 代码完成，待 200 条标注集质量门禁与个人微信 E2E 验收 |
| 目标平台 | Hermes Agent 个人微信 Weixin iLink Bot |
| 交付形式 | 第三方 Hermes platform plugin |
| 目标版本 | Hermes Agent `c661785f872b5647fbac7c138d965180783bd9af`（升级前重新验证） |

## 1. 背景

Hermes 的个人微信适配器通过腾讯 iLink Bot API 长轮询接收消息。同一联系人目前长期使用同一个 Hermes gateway session；多个无关话题会逐渐堆积到同一活动上下文中。

Hermes 自带上下文压缩，可以防止会话直接超过模型窗口，但压缩后的长会话仍然存在三个问题：

- 不同话题互相污染，降低回答相关性；
- 每轮仍携带压缩后的长前缀，增加成本；
- Memory 提炼和新 Session 初始化只有在自然会话边界上才能充分发挥作用。

本项目为个人微信提供“模拟话题”：微信本身没有 Thread/Topic 元数据，插件在消息进入 Hermes gateway 前决定当前 `topic_id`，再通过 Hermes 官方 `SessionSource` 路由到独立 Session。

## 2. 术语

为避免混淆，本 SPEC 固定使用以下术语：

- **Topic**：插件维护的逻辑话题，用于选择 Hermes 路由范围。
- **Session Key**：Hermes 根据 `SessionSource` 通过 `build_session_key()` 生成的稳定路由键。
- **Session ID**：Hermes 管理的运行期会话实例标识，插件不保存、不构造。
- **Transcript**：Hermes 持久化的原始会话记录；切换 Topic 不删除它。
- **Active Context**：本轮实际发送给模型的有限上下文，可被 Hermes 压缩。
- **Memory**：Hermes 跨 Session 注入的提炼信息，不等于完整 Transcript。
- **Routing Context**：仅供自动话题判断使用的有限近期用户消息片段，不作为历史记录来源。

## 3. 目标与非目标

### 3.1 Must Have

1. 个人微信 DM 可以拥有多个独立 Topic，每个 Topic 对应不同 Hermes Session Key。
2. 用户可以通过自然中文或 `/new` 显式开启新 Topic。
3. 插件可以保守地检测明显的新话题，并自动切换。
4. 旧 Topic 的 Transcript 由 Hermes 原样保留，可以切回并继续。
5. 新 Topic 使用干净 Active Context，同时继续获得 Hermes Memory。
6. 支持查看 Topic 列表、当前 Topic、切换 Topic和撤销最近一次自动切换。
7. 插件重启后，当前 Topic 和已存在 Topic 的路由保持稳定。
8. 检测失败、超时或低置信度时必须留在当前 Topic，不得丢消息。

### 3.2 Nice to Have

- 后台生成更好的标题和简短 Topic 摘要；
- 隐藏长期未使用的 Topic，但不删除 Hermes Transcript；
- 为特定联系人配置确定性路由规则；
- 提供自动检测质量指标和调试日志。

### 3.3 Out of Scope

- 修改腾讯 iLink Bot API；
- 微信群 Topic；v1 只支持 DM；
- 微信、Telegram 等平台之间共享 Topic；
- 自建 Hermes SessionDB、上下文压缩或长期记忆系统；
- 物理删除旧 Transcript；
- 将完整微信聊天内容复制到插件自己的数据文件。

## 4. 扩展策略

### 4.1 插件身份

插件注册为独立平台 `weixin_topics`，使用个人微信 iLink Bot API。启用时必须停用内置 `weixin`，避免两个长轮询客户端同时消费同一账号消息。

```yaml
platforms:
  weixin:
    enabled: false
  weixin_topics:
    enabled: true
```

插件优先复用 Hermes 内置 Weixin transport 的公开或稳定实现。如果当前版本没有可复用的正式 seam，则将经过锁版验证的 iLink transport 实现放入插件内部，并记录上游来源和 commit；不得依赖未验证的私有方法继承链。

### 4.2 实施前技术门禁

编码前必须用锁定版本完成一个最小 Spike：

1. 构造两个相同 `chat_id`、不同 `thread_id` 的 Weixin DM `SessionSource`；
2. 使用官方 `build_session_key()`；
3. 证明两个 key 不同；
4. 分别投递消息并证明 Session 历史隔离；
5. 使用相同 `thread_id` 重启 gateway 后，证明恢复到相同 Session Key；
6. 确认插件注册名不会与内置 `weixin` 冲突。

若该 Spike 失败，先为 Hermes 提交最小的正式 seam 扩展，不得回退到手工拼接或 hash Session Key。

## 5. Session 路由设计

### 5.1 单一事实来源

插件不直接创建或保存 Hermes Session ID。插件只为消息补充 Topic 路由信息：

```python
source = adapter.build_source(
    chat_id=peer_id,
    chat_type="dm",
    user_id=peer_id,
    thread_id=topic_id,
)
```

Hermes 使用：

```python
session_key = build_session_key(source)
```

概念格式为：

```text
agent:<profile>:weixin_topics:dm:<peer_id>:<topic_id>
```

具体格式由 Hermes 决定，插件不得依赖字符串布局。

### 5.2 生命周期

- Topic 首条消息第一次使用新 Session Key 时，Hermes 自动创建 Session；
- 切换回旧 Topic 时，重新使用相同 Topic 路由，Hermes 恢复旧 Session；
- Topic 切换不调用 `/clear`，不删除旧 Transcript；
- Hermes 继续负责上下文压缩、Memory、Session 持久化和 `session_search`；
- 插件故障时，消息回退到当前 Topic，而不是创建未知 Session。

### 5.3 旧内置 Weixin Session

由于插件平台名为 `weixin_topics`，原内置 `weixin` Session Key 不会自动变成新插件的默认 Topic。v1 行为：

- 原 Session 保留在 Hermes 中，可以通过 `session_search` 查找；
- Hermes Memory 继续跨新 Session 生效；
- 不自动复制或改写原 Transcript；
- 自动迁移旧 Session Key 属于后续独立迁移功能。

## 6. Module 设计

### 6.1 总体数据流

```text
iLink long-poll
  → WeixinTopicsAdapter（保留官方批量合并行为）
  → TopicRoutingModule.decide(message)
      → TopicStore
      → 可选 TopicBoundaryDetector
  → RoutingDecision
  → 使用 topic_id 构造 SessionSource
  → BasePlatformAdapter.handle_message(event)
  → GatewayRunner 授权、build_session_key、排队、运行 Agent
  → iLink 回复
```

Topic 检测必须发生在 Weixin 文本分片完成批量合并之后，避免把同一条被 iLink 拆分的长消息误判成多个话题。

### 6.2 TopicRoutingModule Interface

外部只暴露一个主要 Interface：

```python
class TopicRoutingModule:
    async def decide(self, message: MessageEvent) -> RoutingDecision:
        """决定消息应被消费、回复或路由到哪个 topic_id。"""
```

返回值：

```python
@dataclass(frozen=True)
class RoutingDecision:
    action: Literal["route", "reply"]
    topic_id: str | None = None
    content: str | None = None
    reply: str | None = None
    reason: Literal["current", "explicit", "rule", "detected", "switch", "undo"] | None = None
```

Interface 不暴露 Session ID、文件路径、LLM client 或数据库操作。Adapter 根据决策发送回复或构造 `SessionSource`。

### 6.3 决策顺序

```text
1. 显式 Topic 命令
2. 用户配置的确定性规则
3. 本地低成本粗筛
4. LLM TopicBoundaryDetector
5. 当前 Topic
```

确定性规则必须先于概率性判断。

## 7. Topic 持久化

### 7.1 存储选择

使用 Python 标准库 SQLite，路径：

```text
~/.hermes/state/weixin_topics.sqlite3
```

SQLite 提供事务、唯一约束和崩溃恢复，避免自行实现跨平台 JSON file lock。数据库文件权限应限制为当前用户可读写。

### 7.2 最小数据模型

```sql
CREATE TABLE peer_state (
    account_id TEXT NOT NULL,
    peer_id TEXT NOT NULL,
    current_topic_id TEXT NOT NULL,
    previous_topic_id TEXT,
    revision INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, peer_id)
);

CREATE TABLE topics (
    account_id TEXT NOT NULL,
    peer_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, peer_id, topic_id)
);

CREATE TABLE processed_messages (
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (account_id, message_id)
);
```

约束：

- `topic_id` 使用 ULID 或 UUID，不使用秒级时间戳；
- 不保存 `hermes_session_id`；
- 不保存完整 Transcript；
- 不永久保存 `trigger_message`；
- `processed_messages` 用于抵御 iLink 重复投递，并按固定保留期清理；
- 当前 Topic 切换采用事务和 revision compare-and-swap。

自动检测所需 Routing Context 最多保存最近 4 条用户消息，每条限制长度，并允许通过配置完全关闭持久化。它不作为历史记录来源。

## 8. 用户交互

### 8.1 显式命令

| 输入 | 行为 |
| --- | --- |
| `/new <内容>`、`新话题：<内容>`、`换个话题，<内容>` | 创建 Topic，并把 `<内容>` 作为新 Session 的第一条消息 |
| `/new`、`新话题`、`换话题` | 创建未命名 Topic；命令被消费，下一条实质消息作为第一条内容 |
| `话题列表` | 显示最近 Topic 和稳定短编号 |
| `当前话题` | 显示当前 Topic |
| `切到 <编号>` | 切回旧 Topic |
| `撤销切换` | 回到最近一个 Topic；不删除新 Topic |
| `归档当前话题` | 从默认列表隐藏当前 Topic；不删除 Transcript |

MVP 不提供物理删除命令。

### 8.2 通知策略

- 显式命令：返回简短确认；
- 自动检测：默认静默切换，避免频繁打扰；
- 自动切换后首次回答可附带一行可撤销提示，例如：`已作为新话题处理；回复“撤销切换”可返回。`

## 9. 自动话题检测

### 9.1 设计原则

误切换的成本高于漏切换，因此检测器必须偏保守：

- 显式延续词，如“继续”“刚才那个”“再解释一下”，禁止自动切换；
- Topic 创建后的最初若干轮启用冷却期；
- 短确认、代词型追问和引用回复不调用 LLM；
- 检测超时、异常、非法 JSON 或低置信度一律保持当前 Topic；
- 自动检测不得阻止 Hermes 官方上下文压缩。

### 9.2 检测输入

```json
{
  "current_topic_title": "邮件推送队列重构",
  "recent_user_messages": ["...", "...", "..."],
  "current_message": "我还想问一下下个月去东京怎么安排",
  "turn_count": 18
}
```

只提供判断所需的最小内容，不发送完整 Transcript。

### 9.3 输出

```json
{
  "is_new_topic": true,
  "confidence": 0.96,
  "suggested_title": "东京旅行安排"
}
```

规则：

- `confidence >= 0.90` 才允许自动切换；
- 低于阈值继续当前 Topic；
- `suggested_title` 只作为显示元数据，不影响 Session Key；
- 自动创建必须把触发消息投递到新 Topic，不得吞掉消息；
- 标题优化和摘要生成在消息路由完成后异步执行。

### 9.4 质量门禁

发布自动检测前，使用至少 200 条人工标注的中文连续/换题样本评估：

- 自动切换 precision ≥ 95%；
- 明显换题 recall ≥ 60%；
- LLM 超时或错误时错误切换数为 0；
- 自动判断附加延迟有明确 p95 指标，并设置硬超时。

达不到 precision 门禁时，保留显式命令功能并默认关闭自动检测。

## 10. 配置

```yaml
platforms:
  weixin:
    enabled: false

  weixin_topics:
    enabled: true
    extra:
      account_id: "..."
      token: "..."
      base_url: "https://ilinkai.weixin.qq.com"
      cdn_base_url: "https://novac2c.cdn.weixin.qq.com/c2c"
      dm_policy: allowlist
      allow_from: ["peer-id"]
      group_policy: disabled
      text_batch_delay_seconds: 3.0
      text_batch_split_delay_seconds: 5.0

      topics:
        auto_detect: true
        confidence_threshold: 0.90
        detector_timeout_seconds: 3
        recent_user_messages: 4
        cooldown_turns: 4
        show_auto_switch_hint: false
```

配置原则：

- iLink、授权和批量合并字段与官方 Weixin Adapter 保持一致；
- 群聊固定关闭；
- 自动检测可以关闭，显式命令仍可用；
- 辅助模型复用 Hermes 官方 auxiliary 配置，不在插件中新增 provider 配置体系；
- 未配置辅助模型或调用失败时自动检测关闭，不影响正常消息。

## 11. 并发与失败处理

| 场景 | 行为 |
| --- | --- |
| 相同 iLink `message_id` 重复投递 | 幂等忽略，不重复创建 Topic |
| 同一联系人并发消息 | 按 peer 串行执行 Topic 决策；Hermes 继续管理 Session 队列 |
| 两条消息同时要求新 Topic | SQLite 事务 + revision CAS，只允许一次指针提交 |
| 检测器超时/失败 | 路由到事务开始时的当前 Topic |
| Topic 元数据损坏 | 停止自动切换并告警；不得静默丢弃映射或重建覆盖 |
| 创建 Topic 后进程崩溃 | Topic 元数据已提交；首条消息重投时由 message id 幂等恢复 |
| Hermes 首次创建新 Session 失败 | 保留 Topic，返回可重试错误；不得把消息偷偷投到旧 Topic |
| 标题或摘要生成失败 | 保留默认标题，不影响 Session 和消息 |
| 自动误切换 | 用户执行“撤销切换”返回 previous topic |

LLM、网络和标题生成不得在 SQLite 写事务内执行。

## 12. 测试与验收

### 12.1 单元测试

- 命令解析和内容提取；
- RoutingDecision 的所有分支；
- 确定性规则优先于 LLM；
- 连续话题、明显换题、短回复、引用回复；
- 置信度阈值、超时、非法 JSON；
- SQLite 事务、CAS、幂等和重启恢复；
- ULID/UUID 唯一性；
- 不保存 Session ID 和完整 Transcript。

### 12.2 集成测试

- 相同 `peer_id`、不同 `topic_id` 生成不同 Session Key；
- 切回旧 Topic 恢复同一 Session Key 和历史；
- 两个联系人即使 Topic ID 相同也互相隔离；
- iLink 文本分片先合并、后检测；
- Hermes 授权仍在 gateway 中生效；
- Hermes 上下文压缩只影响目标 Session；
- gateway 重启后 Topic 指针和路由稳定；
- 内置 `weixin` 停用，只有插件消费 iLink 消息。

### 12.3 E2E 验收

1. 个人微信发送普通消息，进入默认 Topic；
2. 发送 `新话题：讨论邮件队列`，内容进入新 Session；
3. 发送后续追问，继续同一 Topic；
4. 发送明显无关的新问题，达到高置信度时自动切换；
5. 发送 `撤销切换`，回到旧 Topic；
6. 发送 `话题列表` 并切回任一旧 Topic，验证历史连续；
7. 重启 gateway 后重复第 6 步；
8. 使用 `session_search` 找到旧 Session 内容；
9. 验证没有 Transcript 被删除或复制到插件数据库。

## 13. 实施路线图

### Phase 0：官方 seam 验证

- 锁定 Hermes Agent commit/tag；
- 完成 `thread_id` Session Key Spike；
- 验证第三方 platform plugin 加载和内置 Weixin 停用；
- 决定复用 transport 还是锁版内置 transport 实现。

### Phase 1：可回退的显式多 Topic MVP

- 个人微信 iLink transport；
- TopicRoutingModule；
- SQLite TopicStore；
- `新话题`、`话题列表`、`切到`、`当前话题`、`撤销切换`；
- 重启恢复、幂等和并发测试；
- 不包含 LLM 自动检测。

### Phase 2：保守自动检测

- Routing Context；
- auxiliary 模型调用；
- 高置信度自动切换；
- 异步标题优化；
- 标注集和质量门禁；
- 默认静默，支持撤销。

### Phase 3：可观测性与发布

- 自动切换 precision/latency/failure 指标；
- 用户文档、安装和回滚说明；
- 上游 iLink transport 差异检查；
- 可选确定性规则与软归档。

规则引擎、定时归档、标签、删除和跨平台同步不阻塞 v1 发布。

## 14. 兼容性与回滚

- 插件不修改 `BasePlatformAdapter` Interface；
- 插件不手工生成 Session Key；
- 插件停用后可重新启用内置 `weixin`；
- Topic 数据库删除不会删除 Hermes Transcript，但会失去 Topic 名称和当前指针，因此卸载前应备份；
- 原内置 Weixin 历史保留，不做自动破坏性迁移；
- Hermes 升级前必须运行 Phase 0 的 Session Key 和 transport 集成测试。

## 15. 风险

| 风险 | 优先级 | 缓解 |
| --- | --- | --- |
| 错误自动切换导致上下文割裂 | 高 | 0.90 阈值、precision 门禁、冷却期、撤销切换 |
| 上游 Weixin 私有实现变化 | 高 | 锁定版本、来源记录、升级集成测试 |
| 插件与内置适配器同时消费 | 高 | 启动检查并拒绝双启 |
| Topic 元数据与 Session Key 不一致 | 高 | 只保存 topic_id；Session Key 始终由 Hermes 生成 |
| 重复投递或并发创建 | 中 | message_id 幂等、SQLite 事务、peer 串行化 |
| 自动检测成本和延迟 | 中 | 本地粗筛、短超时、辅助模型、失败时继续当前 Topic |
| 敏感聊天内容重复存储 | 中 | Routing Context 有界、文件权限、可关闭持久化 |
| Topic 数量增长 | 低 | 列表分页和软归档，不删除 Transcript |

## 16. 参考

- [Hermes Weixin 个人微信文档](https://github.com/nousresearch/hermes-agent/blob/main/website/docs/user-guide/messaging/weixin.md)
- [Hermes Gateway Internals](https://github.com/nousresearch/hermes-agent/blob/main/website/docs/developer-guide/gateway-internals.md)
- [Hermes Session Lifecycle](https://github.com/nousresearch/hermes-agent/blob/main/docs/session-lifecycle.md)
- [Adding a Platform Adapter](https://github.com/nousresearch/hermes-agent/blob/main/website/docs/developer-guide/adding-platform-adapters.md)
- Hermes 源码：`gateway/session.py`、`gateway/platforms/base.py`、`gateway/platforms/weixin.py`

## 17. 评审结论

只有 Phase 0 的全部门禁通过后，才能开始 Phase 1。Phase 1 验证人工多 Topic 路由稳定后，才能开始 Phase 2 自动检测。
