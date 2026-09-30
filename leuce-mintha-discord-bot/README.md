# Leuce & Mintha Discord AI

A modular Discord AI chatbot inspired by Leuce and Mintha from *Aether Gazer*, using Gemini 3.5 Flash-Lite and designed for Render.

## Features

- Gemini 3.5 Flash-Lite
- Leuce + Mintha dual-character persona
- `lm!hades <text>`
- `lm!reset`
- `lm!ping`
- `lm!hadeshelp`
- Replies to direct `@mentions` in guilds
- Replies to messages in DMs
- Per-user/per-channel conversation memory
- Memory TTL and conversation cap
- Discord 2,000-character response splitting
- Per-user cooldown
- Concurrent-request limit
- Gemini retry handling
- Render health endpoint
- No API keys stored in source code

## 1. Discord bot setup

Create an application in the Discord Developer Portal, add a bot, and copy its token.

Under the bot's privileged gateway intents, enable **Message Content Intent**. The bot reads normal message text and mention text, so this intent is required.

Invite the bot to the server with permission to view and send messages in the channels where you will use it.

## 2. Gemini API key

Create a Gemini API key in Google AI Studio.

Do not put the real key in GitHub.

The default model is:

`gemini-3.5-flash-lite`

## 3. Local setup

Create a virtual environment and install dependencies:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the two secrets:

```env
DISCORD_TOKEN=your_discord_token
GEMINI_API_KEY=your_gemini_api_key
```

Run:

```powershell
python main.py
```

## 4. Render

Use **Web Service** with the Free plan. This repository includes `render.yaml` with the build/start settings and `/health` health check.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
python main.py
```

Set these environment variables in Render:

```text
DISCORD_TOKEN
GEMINI_API_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
BOT_PREFIX=lm!
MAX_HISTORY=16
MAX_OUTPUT_TOKENS=768
USER_COOLDOWN=2.0
MAX_CONCURRENT_REQUESTS=3
REQUEST_TIMEOUT=45
MEMORY_TTL_SECONDS=21600
MAX_CONVERSATIONS=500
MAX_INPUT_CHARS=12000
```

Do not create a committed `.env` containing real secrets.

## 5. Keeping the free Render service awake

Render free Web Services can spin down after 15 minutes without inbound traffic. This bot exposes:

```text
https://YOUR-SERVICE.onrender.com/health
```

A free external HTTP monitor such as UptimeRobot can request `/health` every 5 minutes.

Free Render can still restart a service, and this bot's conversation memory is in RAM, so memory is lost whenever the process restarts or spins down.

## Commands

```text
lm!hades <message>
lm!reset
lm!ping
lm!hadeshelp
```

In a server, you can also mention the bot:

```text
@Leuce & Mintha hello
```

In a DM, just send a normal message.

## Memory

Memory is keyed by Discord user ID + channel ID. It is bounded by `MAX_HISTORY`, `MEMORY_TTL_SECONDS`, and `MAX_CONVERSATIONS`.

`lm!reset` clears the current user's conversation in the current channel.

## Project structure

```text
leuce-mintha-discord-bot/
├── main.py
├── bot.py
├── config.py
├── gemini.py
├── memory.py
├── personality.py
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
└── README.md
```

## Updating

```powershell
git add .
git commit -m "Update Leuce and Mintha bot"
git push
```

With Render auto-deploy enabled, pushing the connected branch triggers a new deployment.

This is a fan-made project and is not an official Aether Gazer, Yongshi, Discord, or Google product.
