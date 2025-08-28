import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import config
from handlers.admin_handlers import AdminHandlers
from handlers.callback_handlers import CallbackHandlers
from handlers.message_handlers import MessageHandlers
from handlers.user_handlers import UserHandlers

logger = logging.getLogger(__name__)


class EventBot:
    """Main Telegram Event Bot class"""

    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.user_data = {}  # Store user data for event creation

        # Initialize handlers
        self.admin_handlers = AdminHandlers(self)
        self.user_handlers = UserHandlers(self)
        self.callback_handlers = CallbackHandlers(self)
        self.message_handlers = MessageHandlers(self)

        self.setup_handlers()

    def setup_handlers(self):
        """Setup command and callback handlers"""
        # Admin commands
        self.application.add_handler(
            CommandHandler("admin", self.admin_handlers.admin_menu)
        )
        self.application.add_handler(
            CommandHandler("create_event", self.admin_handlers.create_event)
        )
        self.application.add_handler(
            CommandHandler("list_events", self.admin_handlers.list_events)
        )
        self.application.add_handler(
            CommandHandler("event_users", self.admin_handlers.event_users)
        )
        self.application.add_handler(
            CommandHandler("notify_users", self.admin_handlers.notify_users)
        )
        self.application.add_handler(
            CommandHandler("post_event_card", self.admin_handlers.post_event_card)
        )
        self.application.add_handler(
            CommandHandler("rsvp_stats", self.admin_handlers.show_rsvp_stats)
        )
        self.application.add_handler(
            CommandHandler("check_users", self.admin_handlers.check_user_status)
        )
        self.application.add_handler(
            CommandHandler("test_channel", self.admin_handlers.test_channel)
        )

        # Public commands
        self.application.add_handler(CommandHandler("start", self.user_handlers.start))
        self.application.add_handler(
            CommandHandler("events", self.user_handlers.show_events)
        )

        # Message handlers
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, self.message_handlers.handle_message
            )
        )
        self.application.add_handler(
            MessageHandler(filters.PHOTO, self.message_handlers.handle_photo_message)
        )

        # Callback handlers
        self.application.add_handler(
            CallbackQueryHandler(self.callback_handlers.handle_callback)
        )

    def run(self):
        """Run the bot"""
        print("Запуск бота регистрации на мероприятия...")
        self.application.run_polling()
