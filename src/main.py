"""
Process entry point for TFS-Bot.

Loads the environment, builds BotConfig,
and starts the Discord client. Run as
`python -m src.main` from the repository
root.
"""

from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from .bot import TFSBot
from .config import BotConfig


async def main() -> None:
    """
    Start the bot and block until the
    Discord connection ends.
    """
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    config = BotConfig.from_environment()
    bot = TFSBot(config)

    await bot.start(config.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
