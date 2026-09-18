# Hermes WeChat Official Account Plugin

A Hermes Agent platform plugin for direct text messages received through a WeChat Official Account callback.

## Install

Place `plugins/platforms/wechat_official/` in the Hermes Agent `plugins/platforms/` directory, then configure these environment variables:

```text
WECHAT_OFFICIAL_APP_ID=...
WECHAT_OFFICIAL_APP_SECRET=...
WECHAT_OFFICIAL_TOKEN=...
WECHAT_OFFICIAL_PORT=8080
WECHAT_OFFICIAL_ALLOWED_USERS=openid-1,openid-2
```

Set the Official Account callback URL to `https://<your-host>/wechat/callback` and configure the same callback token. Hermes denies users by default; set `WECHAT_OFFICIAL_ALLOWED_USERS` before enabling the channel.

The adapter acknowledges callbacks immediately, then sends Hermes's response through the Official Account text-message API. Hermes owns session routing and `/new` resets.

## Scope

- Direct text messages only
- Plaintext Official Account callbacks with validated signatures
- No group chats, media messages, encrypted callbacks, or custom session expiry

## Check

```text
python -m unittest tests/test_wechat_official_security.py
```
