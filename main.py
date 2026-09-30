import logging

from leuce_mintha_bot.bot import LeuceMinthaBot
from leuce_mintha_bot.config import DISCORD_TOKEN, validate
from leuce_mintha_bot.web import start_web_server


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> None:
    validate()
    start_web_server()
    bot = LeuceMinthaBot()
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
