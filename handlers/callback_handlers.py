import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import config
from database import db
from utils.keyboard_utils import create_rsvp_keyboard
from utils.message_utils import format_event_card_message

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Callback handlers for inline keyboard interactions"""

    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()

        logger.info(f"Callback received: {query.data} from user {query.from_user.id}")

        if query.data.startswith("register_"):
            await self.handle_registration(query)
        elif query.data.startswith("rsvp_"):
            await self.handle_rsvp_response(query)
        elif query.data.startswith("post_card_"):
            await self.handle_post_card_selection(query)
        elif query.data.startswith("view_stats_"):
            await self.handle_view_stats_selection(query)
        elif query.data.startswith("check_users_"):
            await self.handle_check_users_selection(query)
        elif query.data.startswith("admin_"):
            await self.handle_admin_callback(query)
        elif query.data.startswith("notify_event_"):
            await self.handle_notify_event_selection(query)
        elif query.data.startswith("create_"):
            await self.handle_event_creation_step(query)
        else:
            logger.warning(f"Неизвестные данные обратного вызова: {query.data}")

    async def handle_registration(self, query):
        """Handle event registration"""
        event_id = int(query.data.split("_")[1])
        user = query.from_user

        # Check if already registered
        if db.is_user_registered(event_id, user.id):
            await query.edit_message_text(
                "✅ You're already registered for this event!"
            )
            return

        # Get event details
        event = db.get_event_by_id(event_id)
        if not event:
            await query.edit_message_text("❌ Мероприятие не найдено.")
            return

        # Register user
        success = db.register_user_for_event(
            event_id, user.id, user.username, user.first_name
        )

        if success:
            await query.edit_message_text(
                f"✅ Успешно зарегистрированы на '{event[0]}' {event[2]}!\n"
                "Вы получите уведомление перед мероприятием."
            )
        else:
            await query.edit_message_text("❌ Ошибка регистрации. Попробуйте снова.")

    async def handle_rsvp_response(self, query):
        """Handle RSVP responses"""
        parts = query.data.split("_")
        if len(parts) < 3:
            logger.warning(f"Invalid RSVP callback data: {query.data}")
            await query.answer("Неверный ответ RSVP.")
            return

        event_id = int(parts[1])
        response = parts[2]  # 'иду' or 'не иду'
        user = query.from_user

        # Get event details first
        event = db.get_event_by_id(event_id)
        if not event:
            await query.answer("❌ Event not found.")
            return

        # Set RSVP response
        action_message = db.set_rsvp_response(
            event_id, user.id, user.username, user.first_name, response
        )

        # Get updated RSVP statistics and responses
        stats = db.get_rsvp_stats(event_id)
        recent_responses = db.get_recent_rsvp_responses(event_id)

        # Update the message with current status
        title, description, event_date = event

        # Format event card message with updated stats
        message = f"🎉 *{title}*\n\n"
        if description:
            message += f"📝 {description}\n\n"
        message += f"📅 Дата: {event_date}\n\n"

        # Add RSVP statistics
        message += f"📊 *RSVP Статистика:*\n"
        message += f"✅ иду: {stats['иду']}\n"
        message += f"❌ не иду: {stats['не иду']}\n\n"

        # Add recent responses
        if recent_responses:
            message += "👥 *Последние ответы:*\n"
            for first_name, username, resp in recent_responses:
                name = first_name or "Unknown"
                emoji = "✅" if resp == "иду" else "❌"
                message += f"{emoji} {name}: {resp}\n"
            message += "\n"

        message += "Отметьтесь, пожалуйста:"

        # Create updated keyboard with current stats and user's current response
        reply_markup = create_rsvp_keyboard(event_id, user.id)

        # Update the message
        try:
            await query.edit_message_text(
                text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )
            await query.answer(action_message)
        except Exception as e:
            logger.error(f"Error updating RSVP message: {e}")
            await query.answer(action_message)

    async def handle_post_card_selection(self, query):
        """Handle event selection for posting event card"""
        if not config.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[2])
        event = db.get_event_by_id(event_id)

        if not event:
            await query.answer("❌ Мероприятие не найдено или неактивно.")
            return

        title, description, event_date = event

        # Create RSVP keyboard (no user_id for initial posting)
        reply_markup = create_rsvp_keyboard(event_id)

        # Get current RSVP statistics for message
        stats = db.get_rsvp_stats(event_id)

        # Format event card message with initial stats
        message = f"🎉 *{title}*\n\n"
        if description:
            message += f"📝 {description}\n\n"
        message += f"📅 Дата: {event_date}\n\n"

        # Add RSVP statistics
        message += f"📊 *RSVP Статистика:*\n"
        message += f"✅ иду: {stats['иду']}\n"
        message += f"❌ не иду: {stats['не иду']}\n\n"

        message += "Отметьтесь, пожалуйста:"

        # Post the event card in the chat
        await query.message.reply_text(
            text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
        )

        await query.answer("✅ Карточка мероприятия опубликована!")

    async def handle_view_stats_selection(self, query):
        """Handle event selection for viewing RSVP statistics"""
        if not config.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[2])
        event = db.get_event_by_id(event_id)

        if not event:
            await query.answer("❌ Мероприятие не найдено.")
            return

        stats = db.get_rsvp_stats(event_id)

        text = f"📊 *Статистика RSVP для '{event[0]}'*\n📅 Дата: {event[2]}\n\n"
        text += f"✅ иду: {stats['иду']}\n❌ не иду: {stats['не иду']}\n\n"
        text += "Всего ответов: " + str(stats["иду"] + stats["не иду"])

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

    async def handle_check_users_selection(self, query):
        """Handle event selection for checking user status"""
        if not config.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[2])
        event = db.get_event_by_id(event_id)

        if not event:
            await query.answer("❌ Мероприятие не найдено.")
            return

        # Get all registered users for this event
        user_ids = db.get_registered_users_for_event(event_id)

        if not user_ids:
            await query.edit_message_text(
                "❌ Нет зарегистрированных пользователей для этого мероприятия."
            )
            return

        # Test sending a message to each user
        test_message = (
            "🔍 Это тестовое сообщение для проверки возможности получения уведомлений."
        )
        reachable_users = []
        unreachable_users = []

        for user_id in user_ids:
            try:
                await self.bot.application.bot.send_message(
                    chat_id=user_id, text=test_message
                )
                reachable_users.append((user_id, None, None))
            except Exception as e:
                error_msg = str(e)
                if "bot can't initiate conversation" in error_msg.lower():
                    unreachable_users.append((user_id, None, None))

        # Create status report
        from utils.message_utils import format_user_status_report

        report = format_user_status_report(
            event[0], event[2], reachable_users, unreachable_users
        )

        await query.edit_message_text(report, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_callback(self, query):
        """Handle admin callbacks"""
        from handlers.admin_handlers import AdminHandlers

        admin_handlers = AdminHandlers(self.bot)
        await admin_handlers.handle_admin_callback(query)

    async def handle_notify_event_selection(self, query):
        """Handle event selection for notifications"""
        if not config.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        # Extract event_id from callback data
        event_id = int(query.data.split("_")[2])

        # Store the selected event_id for the notification
        user_id = query.from_user.id
        if user_id not in self.bot.user_data:
            self.bot.user_data[user_id] = {}

        self.bot.user_data[user_id]["notify_event_id"] = event_id
        self.bot.user_data[user_id]["waiting_for"] = "notification_message"
        self.bot.user_data[user_id]["creating_notification"] = True

        # Get event details
        event = db.get_event_by_id(event_id)

        if not event:
            await query.edit_message_text("❌ Мероприятие не найдено.")
            return

        from utils.keyboard_utils import create_back_to_admin_keyboard

        await query.edit_message_text(
            f"📢 *Отправить уведомление*\n\n"
            f"📅 Мероприятие: {event[0]}\n"
            f"📅 Дата: {event[2]}\n\n"
            f"Пожалуйста, отправьте сообщение уведомления:\n\n"
            f'💡 Пример: "Не забудьте взять ноутбук!"\n\n'
            f"Просто введите ваше сообщение и отправьте как обычное сообщение.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=create_back_to_admin_keyboard(),
        )

    async def handle_event_creation_step(self, query):
        """Handle individual steps of event creation"""
        user_id = query.from_user.id

        # Check if user is admin
        if not config.is_admin(user_id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        # Initialize user_data if it doesn't exist
        if user_id not in self.bot.user_data:
            self.bot.user_data[user_id] = {}

        logger.info(f"Event creation step: {query.data} for user {user_id}")

        if query.data == "create_title":
            logger.info(f"Setting up title input for user {user_id}")
            self.bot.user_data[user_id]["creating_event"] = True
            self.bot.user_data[user_id]["waiting_for"] = "title"
            logger.info(f"User data for {user_id}: {self.bot.user_data[user_id]}")
            await query.edit_message_text(
                "📝 Пожалуйста, введите название мероприятия:\n\n"
                "Отправьте сообщение с названием.\n\n"
                "Пример: Командная встреча\n\n"
                "💡 Просто введите название и отправьте как обычное сообщение."
            )

        elif query.data == "create_date":
            self.bot.user_data[user_id]["creating_event"] = True
            self.bot.user_data[user_id]["waiting_for"] = "date"
            await query.edit_message_text(
                "📅 Пожалуйста, введите дату мероприятия:\n\n"
                "Отправьте сообщение с датой в формате ГГГГ-ММ-ДД.\n\n"
                "Пример: 2024-12-25\n\n"
                "💡 Просто введите дату и отправьте как обычное сообщение."
            )

        elif query.data == "create_description":
            self.bot.user_data[user_id]["creating_event"] = True
            self.bot.user_data[user_id]["waiting_for"] = "description"
            await query.edit_message_text(
                "📄 Пожалуйста, введите описание мероприятия:\n\n"
                "Отправьте сообщение с описанием.\n\n"
                "Пример: Ежемесячная синхронизация команды\n\n"
                "💡 Просто введите описание и отправьте как обычное сообщение."
            )

        elif query.data == "create_final":
            await self.create_event_from_dialogue(query)
        elif query.data == "create_clear":
            await self.clear_event_creation_data(query)
        else:
            logger.warning(f"Неизвестный шаг создания мероприятия: {query.data}")
            await query.edit_message_text("❌ Неизвестное действие. Попробуйте снова.")

    async def create_event_from_dialogue(self, query):
        """Create event using the dialogue data"""
        user_id = query.from_user.id

        # Get stored event data
        user_data = self.bot.user_data.get(user_id, {})

        title = user_data.get("event_title", "Без названия")
        event_date = user_data.get("event_date", datetime.now().strftime("%Y-%m-%d"))
        description = user_data.get("event_description", "Описание не предоставлено")

        # Validate that we have at least a title
        if not title or title == "Без названия":
            await query.edit_message_text(
                "❌ Пожалуйста, сначала установите название мероприятия.\n\n"
                "Используйте кнопку '📝 Ввести название мероприятия' для установки названия."
            )
            return

        try:
            event_id = db.create_event(title, description, event_date)

            # Clear the creation data
            if user_id in self.bot.user_data:
                self.bot.user_data[user_id].clear()

            await query.edit_message_text(
                f"✅ Мероприятие успешно создано!\n\n"
                f"📝 Название: {title}\n"
                f"📅 Дата: {event_date}\n"
                f"📄 Описание: {description}\n\n"
                f"ID мероприятия: {event_id}"
            )

        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка создания мероприятия: {str(e)}")

    async def clear_event_creation_data(self, query):
        """Clear event creation data for user"""
        user_id = query.from_user.id

        if user_id in self.bot.user_data:
            self.bot.user_data[user_id].clear()

        await query.edit_message_text(
            "🗑️ Данные создания мероприятия очищены!\n\n"
            "Все поля сброшены. Вы можете начать заново создание мероприятия."
        )
