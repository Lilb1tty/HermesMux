# Hermes WeChat Session Routing

This context defines how the Hermes WeChat channel keeps independent conversation state despite the channel's single underlying Hermes session.

## Language

**WeChat Conversation**:
A direct WeChat chat identified by a stable platform conversation identifier. Group chats are outside this project's initial scope.
_Avoid_: User session, group chat, chat window

**Hermes Session**:
An isolated conversational context managed by Hermes for processing messages.
_Avoid_: Global session, channel session

**Session Binding**:
The durable association between one WeChat Conversation and its Hermes Session.
_Avoid_: Session copy, temporary session

**Session Reset**:
The direct-chat participant's requested replacement of their WeChat Conversation's current Hermes Session.
_Avoid_: Clear history, restart chat

**Conversation Metadata**:
The direct-message chat type and stable platform identifiers supplied to Hermes for authorization and deterministic routing.
_Avoid_: Display names, personal profile data

**WeChat Official Account**:
The official WeChat account integration used as this extension's inbound and outbound bot channel.
_Avoid_: Desktop-client automation, WeCom bot
