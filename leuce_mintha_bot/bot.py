import logging
from typing import Final

import discord
from discord.ext import commands, tasks

from .chat import LeuceMinthaChat
from .config import (
    BOT_PREFIX,
    COOLDOWN_PRUNE_INTERVAL,
    DISCORD_TOKEN,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_THINKING_LEVEL,
    MAX_CONCURRENT_REQUESTS,
    MAX_HISTORY,
    MAX_INPUT_CHARS,
    MAX_OUTPUT_TOKENS,
    MEMORY_PRUNE_INTERVAL,
    MEMORY_TTL_SECONDS,
    MAX_CONVERSATIONS,
    USER_COOLDOWN,
    validate,
)
from .gemini_client import GeminiError, GeminiService
from .memory import ConversationMemory
from .utils import CooldownManager, contains_bot_mention, split_message, strip_bot_mentions
from .web import update_discord_state

logger = logging.getLogger("leuce_mintha")
ALLOWED_MENTIONS: Final = discord.AllowedMentions.none()
MENTION_ONLY_PROMPT: Final = (
    "The user only mentioned you. Give them a natural, brief greeting as Leuce and Mintha."
)


class LeuceMinthaBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None,
            allowed_mentions=ALLOWED_MENTIONS,
        )
        self.leuce_mintha_chat = LeuceMinthaChat(
            gemini=GeminiService(
                api_key=GEMINI_API_KEY,
                model=GEMINI_MODEL,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_level=GEMINI_THINKING_LEVEL,
            ),
            memory=ConversationMemory(
                max_messages=MAX_HISTORY,
                ttl_seconds=MEMORY_TTL_SECONDS,
                max_conversations=MAX_CONVERSATIONS,
            ),
        )
        self.cooldowns = CooldownManager(USER_COOLDOWN)
        self._started_at = discord.utils.utcnow()

    async def setup_hook(self) -> None:
        await self.add_cog(LeuceMinthaCommands(self))
        self.maintenance_loop.start()
        logger.info("Registered commands: %s", ", ".join(sorted(c.name for c in self.commands)))

    async def on_connect(self) -> None:
        logger.info("Connected to Discord Gateway.")

    async def on_disconnect(self) -> None:
        update_discord_state(ready=False)
        logger.warning("Disconnected from Discord Gateway; discord.py will attempt to reconnect.")

    async def on_resumed(self) -> None:
        logger.info("Discord session resumed.")

    async def on_ready(self) -> None:
        username = str(self.user) if self.user else None
        logger.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
        logger.info("Connected to %d guild(s)", len(self.guilds))
        logger.info("Gemini model: %s", GEMINI_MODEL)
        logger.info("Command prefix: %s", BOT_PREFIX)
        logger.info("Max Gemini concurrency: %d", MAX_CONCURRENT_REQUESTS)
        logger.info("Max input characters: %d", MAX_INPUT_CHARS)
        update_discord_state(ready=True, user=username, guild_count=len(self.guilds))
        await self.change_presence(status=discord.Status.online, activity=None)

    @tasks.loop(seconds=MEMORY_PRUNE_INTERVAL)
    async def maintenance_loop(self) -> None:
        removed_memory = self.leuce_mintha_chat.prune_memory()
        removed_cooldowns = self.cooldowns.prune(COOLDOWN_PRUNE_INTERVAL)
        if removed_memory or removed_cooldowns:
            logger.info(
                "Maintenance: removed %d expired conversations and %d stale cooldowns.",
                removed_memory,
                removed_cooldowns,
            )

    @maintenance_loop.before_loop
    async def before_maintenance(self) -> None:
        await self.wait_until_ready()

    @maintenance_loop.error
    async def maintenance_error(self, error: BaseException) -> None:
        logger.exception("Maintenance loop failed: %s", error)

    async def close(self) -> None:
        if self.maintenance_loop.is_running():
            self.maintenance_loop.cancel()
        try:
            await self.leuce_mintha_chat.gemini.close()
        except Exception:
            logger.exception("Failed to close Gemini client cleanly.")
        await super().close()

    def conversation_key(self, message: discord.Message) -> str:
        guild_id = message.guild.id if message.guild else "dm"
        return f"{guild_id}:{message.channel.id}:{message.author.id}"

    async def is_reply_to_bot(self, message: discord.Message) -> bool:
        if not self.user or not message.reference:
            return False
        resolved = message.reference.resolved
        if isinstance(resolved, discord.Message):
            return resolved.author.id == self.user.id
        if message.reference.message_id:
            try:
                replied = await message.channel.fetch_message(message.reference.message_id)
                return replied.author.id == self.user.id
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return False
        return False

    async def handle_ai_message(self, message: discord.Message, content: str) -> None:
        remaining = self.cooldowns.consume(message.author.id)
        if remaining > 0:
            await message.reply(
                f"Please wait {remaining:.1f}s before asking again.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
            return

        if len(content) > MAX_INPUT_CHARS:
            await message.reply(
                f"Keep your message under `{MAX_INPUT_CHARS}` characters.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
            return

        try:
            async with message.channel.typing():
                reply = await self.leuce_mintha_chat.ask(self.conversation_key(message), content)
            await self.send_chunks(message.channel, reply, reply_to=message)
        except RuntimeError as exc:
            logger.warning("AI queue/request failed for user %s: %s", message.author.id, exc)
            await message.reply(
                "Leuce and Mintha couldn't answer right now. Please try again shortly.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
        except discord.HTTPException:
            logger.exception("Discord failed while sending AI response.")
        except Exception:
            logger.exception("Unexpected AI message failure.")
            await message.reply(
                "Something went wrong while talking to Leuce and Mintha.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )

    async def send_chunks(
        self,
        destination: discord.abc.Messageable,
        text: str,
        reply_to: discord.Message | None = None,
    ) -> None:
        chunks = split_message(text)
        for index, chunk in enumerate(chunks):
            if index == 0 and reply_to is not None:
                await reply_to.reply(
                    chunk,
                    mention_author=False,
                    allowed_mentions=ALLOWED_MENTIONS,
                )
            else:
                await destination.send(chunk, allowed_mentions=ALLOWED_MENTIONS)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        await self.process_commands(message)
        if message.content.lstrip().startswith(BOT_PREFIX):
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        mentioned = bool(self.user and contains_bot_mention(message.content, self.user.id))
        replied_to_bot = False if is_dm else await self.is_reply_to_bot(message)

        if not is_dm and not mentioned and not replied_to_bot:
            return

        content = message.content.strip()
        if self.user and mentioned:
            content = strip_bot_mentions(content, self.user.id)

        if not content:
            content = MENTION_ONLY_PROMPT

        await self.handle_ai_message(message, content)


class LeuceMinthaCommands(commands.Cog):
    def __init__(self, bot: LeuceMinthaBot) -> None:
        self.bot = bot

    @commands.command(name="hades", aliases=("chat", "ask", "leuce", "mintha"))
    async def hades_command(self, ctx: commands.Context, *, prompt: str | None = None) -> None:
        if not prompt or not prompt.strip():
            await ctx.reply(
                f"Usage: `{BOT_PREFIX}hades <message>`",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
            return
        prompt = prompt.strip()
        if len(prompt) > MAX_INPUT_CHARS:
            await ctx.reply(
                f"Keep your message under `{MAX_INPUT_CHARS}` characters.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
            return
        try:
            remaining = self.bot.cooldowns.consume(ctx.author.id)
            if remaining > 0:
                await ctx.reply(
                    f"Please wait {remaining:.1f}s before asking again.",
                    mention_author=False,
                    allowed_mentions=ALLOWED_MENTIONS,
                )
                return
            async with ctx.typing():
                reply = await self.bot.leuce_mintha_chat.ask(self.bot.conversation_key(ctx.message), prompt)
            await self.bot.send_chunks(ctx.channel, reply, reply_to=ctx.message)
        except (GeminiError, RuntimeError):
            await ctx.reply(
                "Leuce and Mintha couldn't answer right now. Please try again shortly.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
        except Exception:
            logger.exception("%s%s failed", BOT_PREFIX, ctx.invoked_with or "hades")
            await ctx.reply(
                "Something went wrong while talking to Leuce and Mintha.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )

    @commands.command(name="reset", aliases=("forget", "clear"))
    async def reset_command(self, ctx: commands.Context) -> None:
        self.bot.leuce_mintha_chat.reset(self.bot.conversation_key(ctx.message))
        await ctx.reply(
            "Conversation memory cleared for this chat.",
            mention_author=False,
            allowed_mentions=ALLOWED_MENTIONS,
        )

    @commands.command(name="memory")
    async def memory_command(self, ctx: commands.Context) -> None:
        key = self.bot.conversation_key(ctx.message)
        count = self.bot.leuce_mintha_chat.memory.message_count(key)
        conversations = self.bot.leuce_mintha_chat.memory.conversation_count()
        await ctx.reply(
            (
                f"Conversation memory: `{count}` message(s) in this chat.\n"
                f"Active conversations: `{conversations}`.\n"
                f"Memory expires after `{MEMORY_TTL_SECONDS // 3600}` hour(s)."
            ),
            mention_author=False,
            allowed_mentions=ALLOWED_MENTIONS,
        )

    @commands.command(name="ping")
    async def ping_command(self, ctx: commands.Context) -> None:
        latency = round(self.bot.latency * 1000)
        await ctx.reply(
            f"The connection is functioning. `{latency}ms`.",
            mention_author=False,
            allowed_mentions=ALLOWED_MENTIONS,
        )

    @commands.command(name="status")
    async def status_command(self, ctx: commands.Context) -> None:
        await ctx.reply(
            (
                "**Leuce & Mintha Status**\n"
                f"Model: `{GEMINI_MODEL}`\n"
                f"Guilds: `{len(self.bot.guilds)}`\n"
                f"Memory: `{self.bot.leuce_mintha_chat.memory.conversation_count()}` active conversations\n"
                f"Requests active: `{self.bot.leuce_mintha_chat.active_requests}/{MAX_CONCURRENT_REQUESTS}`\n"
                f"Requests total: `{self.bot.leuce_mintha_chat.total_requests}`\n"
                f"Latency: `{round(self.bot.latency * 1000)}ms`\n"
                "Presence: `Online`"
            ),
            mention_author=False,
            allowed_mentions=ALLOWED_MENTIONS,
        )

    @commands.command(name="hadeshelp", aliases=("help",))
    async def help_command(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title="Leuce & Mintha",
            description=f"Aether Gazer AI chatbot powered by `{GEMINI_MODEL}`.",
        )
        embed.add_field(
            name="Commands",
            value=(
                f"`{BOT_PREFIX}hades <message>` — Chat with Leuce & Mintha\n"
                f"`{BOT_PREFIX}ask <message>` — Chat alias\n"
                f"`{BOT_PREFIX}leuce <message>` — Chat alias\n"
                f"`{BOT_PREFIX}mintha <message>` — Chat alias\n"
                f"`{BOT_PREFIX}reset` / `{BOT_PREFIX}forget` — Clear memory\n"
                f"`{BOT_PREFIX}memory` — Memory information\n"
                f"`{BOT_PREFIX}ping` — Latency\n"
                f"`{BOT_PREFIX}status` — Bot status\n"
                f"`{BOT_PREFIX}hadeshelp` — This help"
            ),
            inline=False,
        )
        embed.add_field(
            name="Chat without a command",
            value=(
                "Mention the bot, send it a DM, or reply directly to one of its messages.\n"
                "Mention-only messages receive a greeting."
            ),
            inline=False,
        )
        embed.set_footer(text="Aether Gazer • Yongshi • Fan-made project")
        await ctx.reply(embed=embed, mention_author=False, allowed_mentions=ALLOWED_MENTIONS)

