#!/usr/bin/env python3
"""
Telegram Event Bot - Main Entry Point

A Telegram bot for event management in closed channels with user registration,
notifications, and admin functionality using python-telegram-bot framework.
"""

import logging

from bot import EventBot
from config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the Telegram Event Bot"""
    try:
        # Create and run bot
        bot = EventBot(config.BOT_TOKEN)
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise


if __name__ == "__main__":
    main()
