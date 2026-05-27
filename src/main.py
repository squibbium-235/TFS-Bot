from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from .bot import TFSBot
from .config import BotConfig


async def main() -> None:
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
