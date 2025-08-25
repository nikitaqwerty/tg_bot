import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config import config
from database import db
from utils.keyboard_utils import (
    create_back_to_admin_keyboard,
    create_event_creation_continue_keyboard,
)

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Message handlers for text input during event creation and notifications"""

    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages for event creation and notifications"""
        user_id = update.effective_user.id

        # Log all incoming messages for debugging
        if update.message.text:
            logger.info(
                f"Received text message from user {user_id}: {update.message.text}"
            )
        elif update.message.photo:
            logger.info(f"Received photo message from user {user_id}")
        else:
            logger.info(
                f"Received message from user {user_id} (type: {type(update.message).__name__})"
            )

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
        # Check if user is in event editing mode
        elif user_id in self.bot.user_data and self.bot.user_data[user_id].get(
            "editing_event"
        ):
            logger.info(
                f"Processing event edit input from user {user_id}: {update.message.text}"
            )
            await self.handle_event_edit_input(update, user_id)
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
                "💡 Совет: Используйте /admin для доступа к панели администратора и создания мероприятий.",
                reply_markup=create_back_to_admin_keyboard(),
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
                f"✅ Название установлено: {user_input}\n\n"
                "Теперь вы можете продолжить настройку мероприятия или вернуться в меню.",
                reply_markup=create_event_creation_continue_keyboard(),
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
                    f"✅ Дата установлена: {user_input}\n\n"
                    "Теперь вы можете продолжить настройку мероприятия или вернуться в меню.",
                    reply_markup=create_event_creation_continue_keyboard(),
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты. Пожалуйста, используйте формат ГГГГ-ММ-ДД.\n"
                    "Пример: 2024-12-25"
                )

        elif waiting_for == "description":
            self.bot.user_data[user_id]["event_description"] = user_input
            self.bot.user_data[user_id]["waiting_for"] = None
            self.bot.user_data[user_id]["creating_event"] = False  # Clear creation mode
            await update.message.reply_text(
                f"✅ Описание установлено: {user_input}\n\n"
                "Теперь вы можете продолжить настройку мероприятия или вернуться в меню.",
                reply_markup=create_event_creation_continue_keyboard(),
            )

        elif waiting_for == "attendee_limit":
            try:
                # Parse and validate the limit
                limit = int(user_input.strip())
                if limit < 0:
                    raise ValueError("Limit must be non-negative")

                if limit == 0:
                    # Set to None to indicate no limit
                    self.bot.user_data[user_id]["attendee_limit"] = None
                    await update.message.reply_text(
                        "✅ Лимит участников снят (без ограничений)\n\n"
                        "Теперь вы можете продолжить настройку мероприятия или вернуться в меню.",
                        reply_markup=create_event_creation_continue_keyboard(),
                    )
                else:
                    self.bot.user_data[user_id]["attendee_limit"] = limit
                    await update.message.reply_text(
                        f"✅ Лимит участников установлен: {limit}\n\n"
                        "Теперь вы можете продолжить настройку мероприятия или вернуться в меню.",
                        reply_markup=create_event_creation_continue_keyboard(),
                    )

                self.bot.user_data[user_id]["waiting_for"] = None
                self.bot.user_data[user_id][
                    "creating_event"
                ] = False  # Clear creation mode

            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат лимита. Пожалуйста, введите положительное число или 0 для снятия лимита.\n"
                    "Пример: 25"
                )

        elif waiting_for == "event_image":
            # Handle image attachment
            if update.message.photo:
                # Get the highest resolution photo
                image_file_id = update.message.photo[-1].file_id
                self.bot.user_data[user_id]["event_image_file_id"] = image_file_id
                self.bot.user_data[user_id]["waiting_for"] = None
                self.bot.user_data[user_id][
                    "creating_event"
                ] = False  # Clear creation mode
                await update.message.reply_text(
                    "✅ Изображение прикреплено к мероприятию!\n\n"
                    "Теперь вы можете продолжить настройку мероприятия или вернуться в меню.",
                    reply_markup=create_event_creation_continue_keyboard(),
                )
            else:
                await update.message.reply_text(
                    "❌ Пожалуйста, отправьте изображение.\n"
                    "Прикрепите фото к сообщению."
                )
        else:
            logger.warning(
                f"Неожиданное состояние ввода для пользователя {user_id}: waiting_for={waiting_for}"
            )
            await update.message.reply_text(
                "❌ Неожиданный ввод. Вернитесь в меню создания для продолжения.",
                reply_markup=create_back_to_admin_keyboard(),
            )

    async def handle_event_edit_input(self, update: Update, user_id: int):
        """Handle user input during event editing"""
        user_input = update.message.text
        waiting_for = self.bot.user_data[user_id].get("waiting_for")

        logger.info(
            f"Handling event edit input for user {user_id}, waiting_for: {waiting_for}, input: {user_input}"
        )

        if waiting_for == "edit_title":
            logger.info(f"Setting edited title for user {user_id}: {user_input}")
            self.bot.user_data[user_id]["event_title"] = user_input
            self.bot.user_data[user_id]["waiting_for"] = None
            self.bot.user_data[user_id]["editing_event"] = False  # Clear editing mode
            await update.message.reply_text(
                f"✅ Название изменено: {user_input}\n\n"
                "Теперь вы можете продолжить редактирование или сохранить изменения.",
                reply_markup=create_back_to_admin_keyboard(),
            )

        elif waiting_for == "edit_date":
            try:
                # Validate date format
                datetime.strptime(user_input, "%Y-%m-%d")
                self.bot.user_data[user_id]["event_date"] = user_input
                self.bot.user_data[user_id]["waiting_for"] = None
                self.bot.user_data[user_id][
                    "editing_event"
                ] = False  # Clear editing mode
                await update.message.reply_text(
                    f"✅ Дата изменена: {user_input}\n\n"
                    "Теперь вы можете продолжить редактирование или сохранить изменения.",
                    reply_markup=create_back_to_admin_keyboard(),
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты. Пожалуйста, используйте формат ГГГГ-ММ-ДД.\n"
                    "Пример: 2024-12-25"
                )

        elif waiting_for == "edit_description":
            self.bot.user_data[user_id]["event_description"] = user_input
            self.bot.user_data[user_id]["waiting_for"] = None
            self.bot.user_data[user_id]["editing_event"] = False  # Clear editing mode
            await update.message.reply_text(
                f"✅ Описание изменено: {user_input}\n\n"
                "Теперь вы можете продолжить редактирование или сохранить изменения.",
                reply_markup=create_back_to_admin_keyboard(),
            )

        elif waiting_for == "edit_attendee_limit":
            try:
                # Parse and validate the limit
                limit = int(user_input.strip())
                if limit < 0:
                    raise ValueError("Limit must be non-negative")

                if limit == 0:
                    # Set to None to indicate no limit
                    self.bot.user_data[user_id]["attendee_limit"] = None
                    await update.message.reply_text(
                        "✅ Лимит участников снят (без ограничений)\n\n"
                        "Теперь вы можете продолжить редактирование или сохранить изменения.",
                        reply_markup=create_back_to_admin_keyboard(),
                    )
                else:
                    self.bot.user_data[user_id]["attendee_limit"] = limit
                    await update.message.reply_text(
                        f"✅ Лимит участников изменен: {limit}\n\n"
                        "Теперь вы можете продолжить редактирование или сохранить изменения.",
                        reply_markup=create_back_to_admin_keyboard(),
                    )

                self.bot.user_data[user_id]["waiting_for"] = None
                self.bot.user_data[user_id][
                    "editing_event"
                ] = False  # Clear editing mode

            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат лимита. Пожалуйста, введите положительное число или 0 для снятия лимита.\n"
                    "Пример: 25"
                )

        elif waiting_for == "edit_event_image":
            # Handle image attachment
            if update.message.photo:
                # Get the highest resolution photo
                image_file_id = update.message.photo[-1].file_id
                self.bot.user_data[user_id]["event_image_file_id"] = image_file_id
                self.bot.user_data[user_id]["waiting_for"] = None
                self.bot.user_data[user_id][
                    "editing_event"
                ] = False  # Clear editing mode
                await update.message.reply_text(
                    "✅ Изображение изменено!\n\n"
                    "Теперь вы можете продолжить редактирование или сохранить изменения.",
                    reply_markup=create_back_to_admin_keyboard(),
                )
            else:
                await update.message.reply_text(
                    "❌ Пожалуйста, отправьте изображение.\n"
                    "Прикрепите фото к сообщению."
                )
        else:
            logger.warning(
                f"Неожиданное состояние ввода редактирования для пользователя {user_id}: waiting_for={waiting_for}"
            )
            await update.message.reply_text(
                "❌ Неожиданный ввод. Вернитесь в меню редактирования для продолжения.",
                reply_markup=create_back_to_admin_keyboard(),
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
                "❌ Неожиданный ввод. Вернитесь в меню администратора для продолжения.",
                reply_markup=create_back_to_admin_keyboard(),
            )

    async def send_notification_to_event_users(
        self, event_id: int, message: str, update: Update
    ):
        """Send notification to all users registered for a specific event"""
        # Get event details
        event = db.get_event_by_id(event_id)

        if not event:
            await update.message.reply_text("❌ Мероприятие не найдено.")
            return

        # Get registered users from both tables
        user_ids = db.get_registered_users_for_event(event_id)

        if not user_ids:
            await update.message.reply_text(
                "❌ Нет зарегистрированных пользователей для этого мероприятия."
            )
            return

        # Send notifications
        notification_text = (
            f"🔔 *Напоминание о мероприятии*\n\n📅 {event[0]} - {event[2]}\n\n{message}"
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

    async def handle_photo_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle photo messages from users"""
        user_id = update.effective_user.id

        # Log photo message
        logger.info(f"Received photo message from user {user_id}")

        if not config.is_admin(user_id):
            logger.info(f"User {user_id} is not admin, ignoring photo message")
            # Send a helpful message to non-admin users
            await update.message.reply_text(
                "👋 Привет! Я бот для управления мероприятиями.\n\n"
                "Для просмотра доступных мероприятий используйте команду /events\n"
                "Если у вас есть вопросы, обратитесь к администратору канала."
            )
            return

        # Check if admin is in event creation mode waiting for image
        if user_id in self.bot.user_data and self.bot.user_data[user_id].get(
            "creating_event"
        ):
            waiting_for = self.bot.user_data[user_id].get("waiting_for")
            if waiting_for == "event_image":
                logger.info(f"Processing event creation image from user {user_id}")
                await self.handle_event_creation_input(update, user_id)
                return

        # Check if admin is in event editing mode waiting for image
        elif user_id in self.bot.user_data and self.bot.user_data[user_id].get(
            "editing_event"
        ):
            waiting_for = self.bot.user_data[user_id].get("waiting_for")
            if waiting_for == "edit_event_image":
                logger.info(f"Processing event edit image from user {user_id}")
                await self.handle_event_edit_input(update, user_id)
                return

        # Photo sent outside of image input context
        logger.info(f"User {user_id} sent photo outside of image input context")
        await update.message.reply_text(
            "📸 Изображение получено!\n\n"
            "💡 Совет: Используйте /admin для доступа к панели администратора.\n"
            "Изображения можно прикреплять к мероприятиям при их создании или редактировании.",
            reply_markup=create_back_to_admin_keyboard(),
        )
