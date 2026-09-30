import asyncio
import logging
import time

import discord
from discord.ext import commands

from config import Config
from gemini import GeminiService
from memory import ConversationMemory
from personality import BOT_PERSONA

log = logging.getLogger("leuce_mintha")


class LeuceMinthaCommands(commands.Cog):
    """Prefix commands for the Leuce & Mintha chatbot."""

    def __init__(self, bot: "LeuceMinthaBot") -> None:
        self.bot = bot

    @commands.command(name="hades")
    @commands.cooldown(1, Config.USER_COOLDOWN, commands.BucketType.user)
    async def hades_command(
        self,
        ctx: commands.Context,
        *,
        prompt: str = "",
    ) -> None:
        """Chat with Leuce and Mintha."""
        prompt = prompt.strip()
        if not prompt:
            await ctx.reply(
                f"Use `{Config.BOT_PREFIX}hades <message>`. ",
                mention_author=False,
            )
            return

        await self.bot.handle_context_chat(ctx, prompt)

    @commands.command(name="reset")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def reset_command(self, ctx: commands.Context) -> None:
        """Clear the current user's conversation in this channel."""
        self.bot.memory.clear((ctx.author.id, ctx.channel.id))
        await ctx.reply(
            "Conversation memory cleared for this channel.",
            mention_author=False,
        )

    @commands.command(name="ping")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def ping_command(self, ctx: commands.Context) -> None:
        """Show bot latency."""
        latency_ms = round(self.bot.latency * 1000)
        await ctx.reply(f"Pong! `{latency_ms}ms`", mention_author=False)

    @commands.command(name="hadeshelp")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def hades_help_command(self, ctx: commands.Context) -> None:
        """Show chatbot commands."""
        prefix = Config.BOT_PREFIX

        embed = discord.Embed(
            title="Leuce & Mintha",
            description=(
                "Aether Gazer fan-made AI chatbot powered by "
                f"`{Config.GEMINI_MODEL}`."
            ),
            color=0x6C63FF,
        )
        embed.add_field(
            name="Commands",
            value=(
                f"`{prefix}hades <message>` — chat with Leuce & Mintha\n"
                f"`{prefix}reset` — clear your current memory\n"
                f"`{prefix}ping` — show this bot's latency\n"
                f"`{prefix}hadeshelp` — show this help"
            ),
            inline=False,
        )
        embed.add_field(
            name="Mention",
            value="@mention the bot in a server to chat without a command.",
            inline=False,
        )
        embed.set_footer(text="Aether Gazer • Yongshi • Fan-made project")
        await ctx.reply(embed=embed, mention_author=False)


class LeuceMinthaBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(
            command_prefix=Config.BOT_PREFIX,
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )

        self.memory = ConversationMemory(
            max_history=Config.MAX_HISTORY,
            ttl_seconds=Config.MEMORY_TTL_SECONDS,
            max_conversations=Config.MAX_CONVERSATIONS,
        )
        self.gemini = GeminiService(
            api_key=Config.GEMINI_API_KEY,
            model=Config.GEMINI_MODEL,
            max_output_tokens=Config.MAX_OUTPUT_TOKENS,
            request_timeout=Config.REQUEST_TIMEOUT,
        )
        self.user_cooldowns: dict[tuple[int, int], float] = {}
        self.request_semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_REQUESTS)

    async def setup_hook(self) -> None:
        # Prefix commands must be explicitly registered when defined in a Cog.
        await self.add_cog(LeuceMinthaCommands(self))
        log.info(
            "Registered prefix commands: %s",
            ", ".join(sorted(command.name for command in self.commands)),
        )

    async def on_ready(self) -> None:
        print(
            f"READY: {self.user} ({self.user.id if self.user else '?'}) "
            f"| guilds={len(self.guilds)} | prefix={Config.BOT_PREFIX}"
        )
        log.info(
            "Logged in as %s (%s)",
            self.user,
            self.user.id if self.user else "?",
        )
        log.info("Connected to %d guild(s).", len(self.guilds))
        log.info(
            "Available commands: %s",
            ", ".join(sorted(command.name for command in self.commands)),
        )
        await self.change_presence(
            status=discord.Status.online,
            activity=None,
        )

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                f"Please wait {error.retry_after:.1f}s before using that command again.",
                mention_author=False,
            )
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                f"Use `{Config.BOT_PREFIX}hades <message>`.",
                mention_author=False,
            )
            return

        log.exception("Command error", exc_info=error)
        await ctx.reply(
            "Something went wrong while handling that command.",
            mention_author=False,
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # Prefix commands need process_commands() because we override on_message.
        if message.content.startswith(Config.BOT_PREFIX):
            await self.process_commands(message)
            return

        prompt = self._extract_prompt(message)
        if prompt is None:
            return

        await self._handle_chat(message, prompt)

    def _extract_prompt(self, message: discord.Message) -> str | None:
        if isinstance(message.channel, (discord.DMChannel, discord.GroupChannel)):
            content = message.content.strip()
            return content or None

        if self.user is None or self.user not in message.mentions:
            return None

        content = message.content.replace(self.user.mention, "")
        content = content.replace(f"<@!{self.user.id}>", "").strip()
        return content or None

    def _conversation_key(self, message: discord.Message) -> tuple[int, int]:
        return (message.author.id, message.channel.id)

    def _is_on_cooldown(self, message: discord.Message) -> float:
        key = self._conversation_key(message)
        now = time.monotonic()
        last = self.user_cooldowns.get(key)

        if last is None:
            self.user_cooldowns[key] = now
            return 0.0

        remaining = Config.USER_COOLDOWN - (now - last)
        if remaining <= 0:
            self.user_cooldowns[key] = now
            return 0.0

        return remaining

    async def _handle_chat(self, message: discord.Message, prompt: str) -> None:
        remaining = self._is_on_cooldown(message)
        if remaining > 0:
            await message.reply(
                f"Slow down a little. Try again in {remaining:.1f}s.",
                mention_author=False,
            )
            return

        if len(prompt) > Config.MAX_INPUT_CHARS:
            prompt = prompt[: Config.MAX_INPUT_CHARS].rstrip() + "…"

        key = self._conversation_key(message)
        history = self.memory.get(key)

        async with self.request_semaphore:
            try:
                async with message.channel.typing():
                    response = await self.gemini.generate(
                        user_text=prompt,
                        history=history,
                        persona=BOT_PERSONA,
                    )
            except Exception:
                log.exception("Gemini request failed.")
                await message.reply(
                    "Leuce and Mintha couldn't answer right now. Please try again.",
                    mention_author=False,
                )
                return

        response = response.strip()
        if not response:
            await message.reply(
                "…Nothing came through. Try saying that again.",
                mention_author=False,
            )
            return

        self.memory.add_turn(key, "user", prompt)
        self.memory.add_turn(key, "model", response)

        for chunk in split_discord_message(response):
            await message.reply(chunk, mention_author=False)

    async def handle_context_chat(
        self,
        ctx: commands.Context,
        prompt: str,
    ) -> None:
        if len(prompt) > Config.MAX_INPUT_CHARS:
            prompt = prompt[: Config.MAX_INPUT_CHARS].rstrip() + "…"

        key = (ctx.author.id, ctx.channel.id)
        history = self.memory.get(key)

        async with self.request_semaphore:
            try:
                async with ctx.typing():
                    response = await self.gemini.generate(
                        user_text=prompt,
                        history=history,
                        persona=BOT_PERSONA,
                    )
            except Exception:
                log.exception("Gemini command request failed.")
                await ctx.reply(
                    "Leuce and Mintha couldn't answer right now. Please try again.",
                    mention_author=False,
                )
                return

        response = response.strip()
        if not response:
            await ctx.reply(
                "…Nothing came through. Try again.",
                mention_author=False,
            )
            return

        self.memory.add_turn(key, "user", prompt)
        self.memory.add_turn(key, "model", response)

        for chunk in split_discord_message(response):
            await ctx.reply(chunk, mention_author=False)


def split_discord_message(text: str, limit: int = 2000) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n", 0, limit)
        if cut < int(limit * 0.50):
            cut = remaining.rfind(" ", 0, limit)
        if cut < int(limit * 0.50):
            cut = limit

        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)

        remaining = remaining[cut:].lstrip()

    return chunks
