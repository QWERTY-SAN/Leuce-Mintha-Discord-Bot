# Leuce & Mintha Discord AI

A modular Discord AI chatbot for Leuce & Mintha from *Aether Gazer*, structured similarly to the Hades Discord AI bot while keeping a separate persona and `lm!` prefix.

## Features

- Python + discord.py
- Gemini API via `google-genai`
- Gemini 3.5 Flash-Lite
- `lm!` prefix commands
- Mention chat, mention-only greetings, DMs, and replies to the bot
- Per-server/channel/user conversation memory
- Automatic memory expiration and bounded memory usage
- Per-user cooldown
- Global Gemini concurrency limit and queue timeout
- Same-conversation locking to prevent out-of-order memory updates
- Gemini timeout/retry handling
- Discord-safe message splitting
- Suppressed bot mentions in generated replies
- `/health` liveness endpoint and `/ready` Discord readiness endpoint
- Automatic maintenance pruning
- Online status only; no Playing/Watching/Listening activity
- Render auto-deploy on commits to `main`

## Commands

```text
lm!hades <message>
lm!ask <message>
lm!chat <message>
lm!leuce <message>
lm!mintha <message>
lm!reset
lm!forget
lm!clear
lm!memory
lm!ping
lm!status
lm!hadeshelp
lm!help
```

You can also mention the bot:

```text
@Leuce & Mintha hello
```

or simply:

```text
@Leuce & Mintha
```

The bot also responds when a user replies directly to one of its messages.

## Project structure

```text
Leuce-Mintha-Discord-Bot/
├── main.py
├── requirements.txt
├── render.yaml
├── .env.example
├── .gitignore
├── .python-version
└── leuce_mintha_bot/
    ├── __init__.py
    ├── bot.py
    ├── chat.py
    ├── config.py
    ├── gemini_client.py
    ├── memory.py
    ├── persona.py
    ├── utils.py
    └── web.py
```

## Discord setup

Enable **Message Content Intent** in the Discord Developer Portal.

Required bot permissions:

- View Channels
- Send Messages
- Read Message History
- Embed Links

Administrator permission is not required.

## Environment

Keep real secrets in Render Environment Variables or a local `.env` file. Never commit `.env`.

```text
DISCORD_TOKEN=...
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash-lite
BOT_PREFIX=lm!
MAX_HISTORY=16
MAX_OUTPUT_TOKENS=768
MAX_INPUT_CHARS=6000
USER_COOLDOWN=2.0
MAX_CONCURRENT_REQUESTS=3
MAX_QUEUE_WAIT=20
REQUEST_TIMEOUT=45
MEMORY_TTL_SECONDS=21600
MAX_CONVERSATIONS=500
MEMORY_PRUNE_INTERVAL=900
COOLDOWN_PRUNE_INTERVAL=3600
MAX_COOLDOWN_ENTRIES=5000
GEMINI_THINKING_LEVEL=low
```

`BOT_PREFIX` is kept in the environment documentation for compatibility, but the bot intentionally uses the fixed `lm!` prefix so it cannot collide with the separate Hades bot's `h!` prefix.

## Render

Use a Web Service:

```text
Build Command: pip install -r requirements.txt
Start Command: python main.py
Health Check Path: /health
Branch: main
Auto Deploy: commit
```

The service exposes:

```text
/health  -> liveness, always HTTP 200 while the process is alive
/ready   -> HTTP 200 only when Discord is connected
```

Render's service should have Auto-Deploy set to **On Commit** as well as the Blueprint's `autoDeployTrigger: commit` configuration.

## Development

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Updating

```powershell
git add .
git commit -m "Update Leuce and Mintha bot"
git push origin main
```

Render then deploys the newest commit automatically when Auto-Deploy is enabled.

## Memory

Memory is stored in RAM and keyed by:

```text
server + channel + user
```

DM conversations use the DM channel instead of a server ID.

A Render restart/redeploy clears in-memory conversations.

## Fan project

This is a fan-made project and is not affiliated with or endorsed by Aether Gazer, Yongshi, Discord, Google, or Render.
