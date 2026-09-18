# HermesMux Topic Routing

HermesMux lets one personal Weixin DM expose several durable logical topics without owning Hermes conversation history.

## Language

**Weixin Peer**:
The stable iLink sender/chat identifier for one direct-message participant.
_Avoid_: Official Account OpenID, group, browser session

**Topic**:
A plugin-owned logical routing scope inside a Weixin Peer. A Topic has a stable UUID and display title.
_Avoid_: Hermes Session, thread transcript, chat window

**Current Topic**:
The Topic that receives an ordinary inbound message for a Weixin Peer.
_Avoid_: Global session, current transcript

**Hermes Session**:
The conversational context owned and persisted by Hermes. Hermes derives its key from `SessionSource`, including the plugin's Topic UUID as `thread_id`.
_Avoid_: Plugin session, SQLite session

**Topic Index**:
The plugin's SQLite metadata containing Topic IDs, titles, current/previous pointers, and bounded message-deduplication IDs. It never contains full Transcripts or Hermes Session IDs.
_Avoid_: Chat database, history store

**Personal Weixin iLink**:
Tencent's long-polling bot API used by Hermes's official personal-Weixin adapter.
_Avoid_: WeChat Official Account, WeCom, desktop automation
