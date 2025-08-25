import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config import config
from database import db

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Message handlers for text input during event creation and notifications"""

    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages for event creation and notifications"""
        user_id = update.effective_user.id

        # Log all incoming messages for debugging
        logger.info(f"Received message from user {user_id}: {update.message.text}")

        if not config.is_admin(user_id):
            logger.info(f"User {user_id} is not admin, ignoring message")
            return

        # Check if user is in event creation mode
        if user_id in self.bot.user_data and self.bot.user_data[user_id].get(
            "creating_event"
        ):
            logger.info(
                f"Processing event creation input from user {user_id}: {update.message.text}"
            )
            await self.handle_event_creation_input(update, user_id)
        # Check if user is in notification creation mode
        elif user_id in self.bot.user_data and self.bot.user_data[user_id].get(
            "creating_notification"
        ):
            logger.info(
                f"Processing notification input from user {user_id}: {update.message.text}"
            )
            await self.handle_notification_input(update, user_id)
        else:
            logger.info(
                f"User {user_id} not in event creation mode. User data: {self.bot.user_data.get(user_id, 'Not found')}"
            )
            # Provide helpful feedback to admin users
            await update.message.reply_text(
                "💡 Совет: Используйте /admin для доступа к панели администратора и создания мероприятий."
            )

    async def handle_event_creation_input(self, update: Update, user_id: int):
        """Handle user input during event creation"""
        user_input = update.message.text
        waiting_for = self.bot.user_data[user_id].get("waiting_for")

        logger.info(
            f"Handling event creation input for user {user_id}, waiting_for: {waiting_for}, input: {user_input}"
        )

        if waiting_for == "title":
            logger.info(f"Setting title for user {user_id}: {user_input}")
            self.bot.user_data[user_id]["event_title"] = user_input
            self.bot.user_data[user_id]["waiting_for"] = None
            self.bot.user_data[user_id]["creating_event"] = False  # Clear creation mode
            await update.message.reply_text(
                f"✅ Title set: {user_input}\n\n"
                "Use /admin to return to the creation menu and continue with other fields."
            )

        elif waiting_for == "date":
            try:
                # Validate date format
                datetime.strptime(user_input, "%Y-%m-%d")
                self.bot.user_data[user_id]["event_date"] = user_input
                self.bot.user_data[user_id]["waiting_for"] = None
                self.bot.user_data[user_id][
                    "creating_event"
                ] = False  # Clear creation mode
                await update.message.reply_text(
                    f"✅ Date set: {user_input}\n\n"
                    "Use /admin to return to the creation menu and continue with other fields."
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid date format. Please use YYYY-MM-DD format.\n"
                    "Example: 2024-12-25"
                )

        elif waiting_for == "description":
            self.bot.user_data[user_id]["event_description"] = user_input
            self.bot.user_data[user_id]["waiting_for"] = None
            self.bot.user_data[user_id]["creating_event"] = False  # Clear creation mode
            await update.message.reply_text(
                f"✅ Description set: {user_input}\n\n"
                "Use /admin to return to the creation menu and create the event."
            )
        else:
            logger.warning(
                f"Неожиданное состояние ввода для пользователя {user_id}: waiting_for={waiting_for}"
            )
            await update.message.reply_text(
                "❌ Неожиданный ввод. Используйте /admin для доступа к меню создания."
            )

    async def handle_notification_input(self, update: Update, user_id: int):
        """Handle user input during notification creation"""
        user_input = update.message.text
        waiting_for = self.bot.user_data[user_id].get("waiting_for")

        logger.info(
            f"Handling notification input for user {user_id}, waiting_for: {waiting_for}, input: {user_input}"
        )

        if waiting_for == "notification_message":
            event_id = self.bot.user_data[user_id].get("notify_event_id")

            if not event_id:
                await update.message.reply_text(
                    "❌ Ошибка: Мероприятие не выбрано. Попробуйте снова."
                )
                self.bot.user_data[user_id]["creating_notification"] = False
                self.bot.user_data[user_id]["waiting_for"] = None
                return

            # Send the notification
            await self.send_notification_to_event_users(event_id, user_input, update)

            # Clear the notification creation state
            self.bot.user_data[user_id]["creating_notification"] = False
            self.bot.user_data[user_id]["waiting_for"] = None
            self.bot.user_data[user_id]["notify_event_id"] = None
        else:
            logger.warning(
                f"Неожиданное состояние ввода уведомления для пользователя {user_id}: waiting_for={waiting_for}"
            )
            await update.message.reply_text(
                "❌ Неожиданный ввод. Используйте /admin для доступа к меню уведомлений."
            )

    async def send_notification_to_event_users(
        self, event_id: int, message: str, update: Update
    ):
        """Send notification to all users registered for a specific event"""
        # Get event details
        event = db.get_event_by_id(event_id)

        if not event:
            await update.message.reply_text("❌ Event not found.")
            return

        # Get registered users from both tables
        user_ids = db.get_registered_users_for_event(event_id)

        if not user_ids:
            await update.message.reply_text("❌ No users registered for this event.")
            return

        # Send notifications
        notification_text = (
            f"🔔 *Event Reminder*\n\n📅 {event[0]} - {event[2]}\n\n{message}"
        )

        sent_count = 0
        failed_count = 0
        blocked_users = []

        for user_id in user_ids:
            try:
                await self.bot.application.bot.send_message(
                    chat_id=user_id, text=notification_text, parse_mode="Markdown"
                )
                sent_count += 1
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to send notification to user {user_id}: {e}")
                failed_count += 1

                # Check if it's a "bot can't initiate conversation" error
                if "bot can't initiate conversation" in error_msg.lower():
                    blocked_users.append(user_id)

        # Send confirmation to admin
        from utils.message_utils import format_notification_status

        status_message = format_notification_status(
            sent_count, len(user_ids), failed_count, blocked_users
        )
        await update.message.reply_text(status_message)
