import os
from typing import List

from dotenv import load_dotenv


class Config:
    """Configuration management for the Telegram Event Bot"""

    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()

        # Bot configuration
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        self.ADMIN_IDS = self._parse_admin_ids(os.getenv("ADMIN_IDS", ""))
        self.CHANNEL_ID = os.getenv("CHANNEL_ID")

        # Database configuration
        self.DATABASE_PATH = "events.db"

        # Validation
        self._validate_config()

    def _parse_admin_ids(self, admin_ids_str: str) -> List[int]:
        """Parse admin IDs from comma-separated string"""
        if not admin_ids_str:
            return []
        return [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

    def _validate_config(self):
        """Validate required configuration values"""
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable is required")

        if not self.ADMIN_IDS:
            raise ValueError("ADMIN_IDS environment variable is required")

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.ADMIN_IDS


# Global configuration instance
config = Config()
