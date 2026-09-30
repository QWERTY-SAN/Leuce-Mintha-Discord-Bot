import logging
import re

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
    MAX_COOLDOWN_ENTRIES,
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
from .memory import ConversationKey, ConversationMemory
from .utils import CooldownManager, contains_bot_mention, split_message, strip_bot_mentions, strip_typed_name
from .web import update_discord_state

logger = logging.getLogger("leuce_mintha")
ALLOWED_MENTIONS = discord.AllowedMentions.none()
MENTION_ONLY_PROMPT = "The user only mentioned you. Give a natural, brief greeting as Leuce and Mintha."


class LeuceMinthaBot(commands.Bot):
    def __init__(self) -> None:
        validate()
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(
            command_prefix=lambda _bot, _message: BOT_PREFIX,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=ALLOWED_MENTIONS,
        )
        self.discord_token = DISCORD_TOKEN
        self.memory = ConversationMemory(MAX_HISTORY, MEMORY_TTL_SECONDS, MAX_CONVERSATIONS)
        self.gemini = GeminiService(GEMINI_API_KEY, GEMINI_MODEL, MAX_OUTPUT_TOKENS, GEMINI_THINKING_LEVEL)
        self.chat = LeuceMinthaChat(self.gemini, self.memory)
        self.cooldowns = CooldownManager(USER_COOLDOWN)
        self.started_at = discord.utils.utcnow()

    async def setup_hook(self) -> None:
        await self.add_cog(LeuceMinthaCommands(self))
        self.maintenance_loop.start()
        logger.info("Commands: %s", ", ".join(sorted(command.name for command in self.commands)))

    async def on_connect(self) -> None:
        logger.info("Connected to Discord Gateway.")

    async def on_disconnect(self) -> None:
        update_discord_state(ready=False)
        logger.warning("Disconnected from Discord Gateway; reconnecting if possible.")

    async def on_resumed(self) -> None:
        logger.info("Discord session resumed.")

    async def on_ready(self) -> None:
        username = str(self.user) if self.user else None
        update_discord_state(ready=True, user=username, guild_count=len(self.guilds))
        await self.change_presence(status=discord.Status.online, activity=None)
        logger.info(
            "Logged in as %s (%s) | guilds=%d | prefix=%s | model=%s",
            self.user, self.user.id if self.user else "?", len(self.guilds), BOT_PREFIX, GEMINI_MODEL,
        )

    @tasks.loop(seconds=MEMORY_PRUNE_INTERVAL)
    async def maintenance_loop(self) -> None:
        removed_memory = self.chat.prune_memory()
        removed_cooldowns = self.cooldowns.prune(COOLDOWN_PRUNE_INTERVAL)
        if removed_memory or removed_cooldowns:
            logger.info("Maintenance removed memory=%d cooldowns=%d", removed_memory, removed_cooldowns)

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
            await self.gemini.close()
        except Exception:
            logger.exception("Failed to close Gemini client cleanly.")
        await super().close()

    def conversation_key(self, message: discord.Message) -> ConversationKey:
        return (message.author.id, message.channel.id)

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

    def extract_prompt(self, message: discord.Message) -> tuple[str | None, str]:
        if isinstance(message.channel, (discord.DMChannel, discord.GroupChannel)):
            text = message.content.strip()
            return (text or None, "duo")
        if self.user is None:
            return None, "duo"

        content = message.content
        mentioned = contains_bot_mention(content, self.user.id)
        if mentioned:
            content = strip_bot_mentions(content, self.user.id)
        else:
            names = {self.user.name, self.user.display_name, "Leuce & Mintha"}
            content, typed = strip_typed_name(content, names)
            mentioned = typed

        if not mentioned and not content.strip() and message.reference is None:
            return None, "duo"
        return (content.strip() or MENTION_ONLY_PROMPT, "duo")

    async def handle_message_chat(self, message: discord.Message, prompt: str, mode: str = "duo") -> None:
        remaining = self.cooldowns.consume(message.author.id)
        if remaining > 0:
            await message.reply(
                f"Please wait {remaining:.1f}s before asking again.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
            return
        if len(prompt) > MAX_INPUT_CHARS:
            await message.reply(
                f"Keep your message under `{MAX_INPUT_CHARS}` characters.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
            return
        key = self.conversation_key(message)
        try:
            async with message.channel.typing():
                reply = await self.chat.ask(key, prompt, mode)
            await self.send_chunks(message.channel, reply, message)
        except (GeminiError, RuntimeError) as exc:
            logger.warning("Chat request failed for user %s: %s", message.author.id, exc)
            await message.reply(
                "Leuce and Mintha couldn't answer right now. Please try again shortly.",
                mention_author=False,
                allowed_mentions=ALLOWED_MENTIONS,
            )
        except discord.HTTPException:
            logger.exception("Discord failed while sending a chat response.")

    async def send_chunks(self, destination: discord.abc.Messageable, text: str, reply_to: discord.Message | None = None) -> None:
        for index, chunk in enumerate(split_message(text)):
            if index == 0 and reply_to is not None:
                await reply_to.reply(chunk, mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            else:
                await destination.send(chunk, allowed_mentions=ALLOWED_MENTIONS)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        await self.process_commands(message)
        if message.content.lstrip().startswith(BOT_PREFIX):
            return

        is_dm = isinstance(message.channel, (discord.DMChannel, discord.GroupChannel))
        mentioned = bool(self.user and contains_bot_mention(message.content, self.user.id))
        replied = False if is_dm else await self.is_reply_to_bot(message)
        if not is_dm and not mentioned and not replied:
            return

        prompt, mode = self.extract_prompt(message)
        if prompt is None:
            return
        await self.handle_message_chat(message, prompt, mode)


class LeuceMinthaCommands(commands.Cog):
    def __init__(self, bot: LeuceMinthaBot) -> None:
        self.bot = bot

    async def _run(self, ctx: commands.Context, prompt: str, mode: str) -> None:
        remaining = self.bot.cooldowns.consume(ctx.author.id)
        if remaining > 0:
            await ctx.reply(f"Please wait {remaining:.1f}s before asking again.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            return
        if len(prompt) > MAX_INPUT_CHARS:
            await ctx.reply(f"Keep your message under `{MAX_INPUT_CHARS}` characters.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            return
        try:
            async with ctx.typing():
                reply = await self.bot.chat.ask((ctx.author.id, ctx.channel.id), prompt, mode)
            await self.bot.send_chunks(ctx.channel, reply, ctx.message)
        except (GeminiError, RuntimeError) as exc:
            logger.warning("%s command failed: %s", ctx.invoked_with, exc)
            await ctx.reply("Leuce and Mintha couldn't answer right now. Please try again shortly.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
        except Exception:
            logger.exception("Unexpected %s command failure", ctx.invoked_with)
            await ctx.reply("Something went wrong while talking to Leuce and Mintha.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)

    @commands.command(name="hades", aliases=("chat", "ask", "duo"))
    async def hades_command(self, ctx: commands.Context, *, prompt: str | None = None) -> None:
        if not prompt or not prompt.strip():
            await ctx.reply(f"Usage: `{BOT_PREFIX}hades <message>`", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            return
        await self._run(ctx, prompt.strip(), "duo")

    @commands.command(name="leuce", aliases=("l",))
    async def leuce_command(self, ctx: commands.Context, *, prompt: str | None = None) -> None:
        if not prompt or not prompt.strip():
            await ctx.reply(f"Usage: `{BOT_PREFIX}leuce <message>`", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            return
        await self._run(ctx, prompt.strip(), "leuce")

    @commands.command(name="mintha", aliases=("m",))
    async def mintha_command(self, ctx: commands.Context, *, prompt: str | None = None) -> None:
        if not prompt or not prompt.strip():
            await ctx.reply(f"Usage: `{BOT_PREFIX}mintha <message>`", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            return
        await self._run(ctx, prompt.strip(), "mintha")

    @commands.command(name="reset", aliases=("forget", "clear"))
    async def reset_command(self, ctx: commands.Context) -> None:
        self.bot.memory.clear((ctx.author.id, ctx.channel.id))
        await ctx.reply("Conversation memory cleared for this chat.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)

    @commands.command(name="memory")
    async def memory_command(self, ctx: commands.Context) -> None:
        key = (ctx.author.id, ctx.channel.id)
        await ctx.reply(
            f"Memory: `{self.bot.memory.message_count(key)}` messages here. Active conversations: `{self.bot.memory.conversation_count()}`.",
            mention_author=False,
            allowed_mentions=ALLOWED_MENTIONS,
        )

    @commands.command(name="ping")
    async def ping_command(self, ctx: commands.Context) -> None:
        await ctx.reply(f"Pong! `{round(self.bot.latency * 1000)}ms`", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)

    @commands.command(name="status")
    async def status_command(self, ctx: commands.Context) -> None:
        await ctx.reply(
            f"**Leuce & Mintha**\nModel: `{GEMINI_MODEL}`\nGuilds: `{len(self.bot.guilds)}`\nActive conversations: `{self.bot.memory.conversation_count()}`\nRequests: `{self.bot.chat.active_requests}/{MAX_CONCURRENT_REQUESTS}` active, `{self.bot.chat.total_requests}` total\nFailed requests: `{self.bot.chat.failed_requests}`\nPresence: `Online`",
            mention_author=False,
            allowed_mentions=ALLOWED_MENTIONS,
        )

    @commands.command(name="hadeshelp", aliases=("help",))
    async def help_command(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title="Leuce & Mintha",
            description=f"Aether Gazer AI chatbot powered by `{GEMINI_MODEL}`.",
            color=0x6C63FF,
        )
        embed.add_field(
            name="Chat",
            value=(
                f"`{BOT_PREFIX}hades <message>` — Duo\n"
                f"`{BOT_PREFIX}leuce <message>` — Leuce focus\n"
                f"`{BOT_PREFIX}mintha <message>` — Mintha focus\n"
                f"`{BOT_PREFIX}chat <message>` — Duo alias\n"
                f"`{BOT_PREFIX}ask <message>` — Duo alias"
            ),
            inline=False,
        )
        embed.add_field(
            name="Memory & status",
            value=(
                f"`{BOT_PREFIX}reset` — Clear memory\n"
                f"`{BOT_PREFIX}memory` — Memory info\n"
                f"`{BOT_PREFIX}ping` — Latency\n"
                f"`{BOT_PREFIX}status` — Bot status"
            ),
            inline=False,
        )
        embed.add_field(
            name="No command needed",
            value="Mention the bot, DM it, or reply directly to one of its messages. Mention-only messages receive a greeting.",
            inline=False,
        )
        embed.set_footer(text="Aether Gazer • Yongshi • Fan-made project")
        await ctx.reply(embed=embed, mention_author=False, allowed_mentions=ALLOWED_MENTIONS)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"Please wait {error.retry_after:.1f}s before asking again.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"Use `{BOT_PREFIX}hadeshelp` for the command list.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
            return
        logger.exception("Command error: %s", error)
        await ctx.reply("Something went wrong while handling that command.", mention_author=False, allowed_mentions=ALLOWED_MENTIONS)
