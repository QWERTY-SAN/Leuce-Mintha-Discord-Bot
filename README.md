# Leuce & Mintha Discord AI

A modular Discord AI chatbot for Leuce and Mintha from *Aether Gazer*, powered by Gemini 3.5 Flash-Lite and designed for Render.

## Commands

```text
lm!hades <message>   Duo conversation
lm!leuce <message>   Leuce-focused conversation
lm!mintha <message>  Mintha-focused conversation
lm!chat <message>    Duo alias
lm!ask <message>     Duo alias
lm!reset             Clear your memory in the current channel
lm!memory            Memory information
lm!ping              Latency
lm!status            Bot status
lm!hadeshelp         Help
```

Aliases:

```text
lm!l <message>
lm!m <message>
```

The bot also responds to a real Discord mention, DMs, and replies to its messages. Mention-only messages such as `@Leuce & Mintha` trigger a greeting.

## Character modes

`lm!hades` / `lm!chat` / `lm!ask` use the duo.

`lm!leuce` makes Leuce the primary speaker.

`lm!mintha` makes Mintha the primary speaker.

The conversation memory is shared by user + channel, so switching between the three modes keeps the same conversation context.

## Discord requirements

Because this bot intentionally uses `lm!` prefix commands and reads normal guild message text, **Message Content Intent must be enabled** in the Discord Developer Portal.

Bot permissions needed:

- View Channels
- Send Messages
- Embed Links
- Read Message History

## Render

```text
Build Command: pip install -r requirements.txt
Start Command: python main.py
Health Check Path: /health
Auto Deploy: On Commit
```

`render.yaml` is configured with `autoDeployTrigger: commit` for the `main` branch.

The bot exposes:

```text
/health   process/liveness endpoint
/ready    Discord-readiness endpoint
```

## Environment

Keep real secrets out of Git:

```env
DISCORD_TOKEN=...
GEMINI_API_KEY=...
```

The default model is `gemini-3.5-flash-lite` and default thinking level is `low`.

## Architecture

```text
main.py
└── leuce_mintha_bot/
    ├── bot.py
    ├── chat.py
    ├── config.py
    ├── gemini_client.py
    ├── memory.py
    ├── persona.py
    ├── utils.py
    └── web.py
```

There is one active architecture. Do not keep a second duplicate root-level bot implementation in the repository.

## Update

```powershell
git add .
git commit -m "Improve Leuce and Mintha chatbot"
git push origin main
```

Render should deploy the new commit automatically when Auto-Deploy is set to On Commit.
