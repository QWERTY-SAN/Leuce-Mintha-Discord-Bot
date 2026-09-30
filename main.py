import logging
import threading

from leuce_mintha_bot.bot import LeuceMinthaBot
from leuce_mintha_bot.config import validate
from leuce_mintha_bot.web import start_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("leuce_mintha")


def main() -> None:
    validate()
    start_web_server()
    bot = LeuceMinthaBot()
    logger.info("Starting Leuce & Mintha bot with prefix lm!.")
    bot.run(bot.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
