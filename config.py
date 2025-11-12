import os
from typing import List, Optional, Union

from dotenv import load_dotenv


class Config:
    """Configuration management for the Telegram Event Bot"""

    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()

        # Bot configuration
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        self.ADMIN_IDS = self._parse_admin_ids(os.getenv("ADMIN_IDS", ""))
        self.CHANNEL_ID = self._parse_channel_id(os.getenv("CHANNEL_ID"))

        # Database configuration
        self.DATABASE_PATH = os.getenv("DATABASE_PATH", "data/events.db")

        # Validation
        self._validate_config()

    def _parse_admin_ids(self, admin_ids_str: str) -> List[int]:
        """Parse admin IDs from comma-separated string"""
        if not admin_ids_str:
            return []
        return [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

    def _parse_channel_id(
        self, channel_id_str: Optional[str]
    ) -> Optional[Union[int, str]]:
        """Normalize CHANNEL_ID from .env

        - Strips whitespace and surrounding quotes
        - Returns '@channelusername' as-is (str)
        - Converts numeric ids like '-1001234567890' to int
        """
        if not channel_id_str:
            return None

        value = channel_id_str.strip()

        # Strip surrounding quotes if present
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1].strip()

        if value.startswith("@"):
            return value

        # Try to interpret as an integer chat id
        try:
            return int(value)
        except (TypeError, ValueError):
            # Fall back to raw string (better than failing validation here)
            return value

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
