import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import config
from database import db
from utils.keyboard_utils import (
    create_event_creation_keyboard,
    create_event_edit_keyboard,
    create_rsvp_keyboard,
)
from utils.message_utils import (
    escape_markdown,
    format_event_card_message,
    format_event_creation_status,
    format_event_edit_status,
)

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
        elif query.data.startswith("save_and_post_"):
            await self.handle_save_and_post(query)
        elif query.data.startswith("post_without_save_"):
            await self.handle_post_without_save(query)
        elif query.data.startswith("view_stats_"):
            await self.handle_view_stats_selection(query)
        elif query.data.startswith("check_users_"):
            await self.handle_check_users_selection(query)
        elif query.data.startswith("edit_event_"):
            await self.handle_edit_event_selection(query)
        elif query.data.startswith("admin_"):
            await self.handle_admin_callback(query)
        elif query.data.startswith("notify_event_"):
            await self.handle_notify_event_selection(query)
        elif query.data.startswith("create_"):
            await self.handle_event_creation_step(query)
        elif query.data.startswith("edit_"):
            await self.handle_event_edit_step(query)
        else:
            logger.warning(f"Неизвестные данные обратного вызова: {query.data}")

    async def handle_registration(self, query):
        """Handle event registration"""
        event_id = int(query.data.split("_")[1])
        user = query.from_user

        # Check if already registered
        if db.is_user_registered(event_id, user.id):
            await query.edit_message_text(
                "✅ Вы уже зарегистрированы на это мероприятие!"
            )
            return

        # Get event details
        event = db.get_event_by_id(event_id)
        if not event:
            await query.edit_message_text("❌ Мероприятие не найдено.")
            return

        title, description, event_date, attendee_limit, _ = event

        # Check if event is at capacity
        if db.is_event_at_capacity(event_id):
            await query.edit_message_text(
                f"❌ К сожалению, мероприятие '{title}' уже заполнено.\n"
                f"Достигнут лимит участников ({attendee_limit})."
            )
            return

        # Register user
        success = db.register_user_for_event(
            event_id, user.id, user.username, user.first_name
        )

        if success:
            # Get updated registration count
            current_count = db.get_registration_count(event_id)
            limit_text = f" (участников: {current_count}"
            if attendee_limit:
                limit_text += f"/{attendee_limit}"
            limit_text += ")"

            from utils.keyboard_utils import create_back_to_admin_keyboard

            await query.edit_message_text(
                f"✅ Успешно зарегистрированы на '{title}' {event_date}!\n"
                f"Вы получите уведомление перед мероприятием.{limit_text}",
                reply_markup=create_back_to_admin_keyboard(),
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
            await query.answer("❌ Мероприятие не найдено.")
            return

        title, description, event_date, attendee_limit, _ = event

        # Check if event is at capacity (only for positive responses)
        if response == "иду" and not db.is_user_registered(event_id, user.id):
            if db.is_event_at_capacity(event_id):
                await query.answer(
                    f"❌ К сожалению, мероприятие '{title}' уже заполнено. "
                    f"Достигнут лимит участников ({attendee_limit})."
                )
                return

        # Set RSVP response
        action_message = db.set_rsvp_response(
            event_id, user.id, user.username, user.first_name, response
        )

        # Update the message with current status

        # Format event card message
        from utils.message_utils import format_event_card_message

        message = format_event_card_message(
            event_id, title, description, event_date, attendee_limit
        )

        # Create updated keyboard with current stats and user's current response
        reply_markup = create_rsvp_keyboard(event_id, user.id)

        # Update the message
        try:
            # Check if the original message has a photo (was sent with reply_photo)
            if query.message.photo:
                # Edit caption for photo messages
                await query.edit_message_caption(
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
            else:
                # Edit text for regular text messages
                await query.edit_message_text(
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
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
        user_id = query.from_user.id

        # Check if user has unsaved changes for this event
        if await self._has_unsaved_changes(user_id, event_id):
            await self._handle_unsaved_changes_warning(query, event_id)
            return

        await self._post_event_card(query, event_id)

    async def _has_unsaved_changes(self, user_id: int, event_id: int) -> bool:
        """Check if user has unsaved changes for the specified event"""
        if user_id not in self.bot.user_data:
            return False

        user_data = self.bot.user_data[user_id]

        # Check if user is currently editing this event
        if (
            user_data.get("editing_event")
            and user_data.get("editing_event_id") == event_id
        ):

            # Check if there are any pending changes
            pending_changes = [
                user_data.get("event_title"),
                user_data.get("event_date"),
                user_data.get("event_description"),
                user_data.get("attendee_limit"),
                user_data.get("event_image_file_id"),
            ]

            return any(change is not None for change in pending_changes)

        return False

    async def _handle_unsaved_changes_warning(self, query, event_id: int):
        """Handle case where user has unsaved changes"""
        from utils.keyboard_utils import create_confirmation_keyboard

        warning_message = (
            "⚠️ *Внимание: У вас есть несохраненные изменения*\n\n"
            "Вы внесли изменения в мероприятие, но не сохранили их.\n"
            "Карточка будет опубликована со старыми данными.\n\n"
            "Хотите сохранить изменения перед публикацией?"
        )

        # Create keyboard with save and proceed options
        reply_markup = create_confirmation_keyboard(
            confirm_callback=f"save_and_post_{event_id}",
            cancel_callback=f"post_without_save_{event_id}",
            confirm_text="💾 Сохранить и опубликовать",
            cancel_text="📤 Опубликовать без сохранения",
        )

        await query.edit_message_text(
            warning_message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
        )

    async def _post_event_card(self, query, event_id: int):
        """Post the event card to the configured channel"""
        # Check if channel is configured
        if not config.CHANNEL_ID:
            await query.answer(
                "❌ Канал не настроен. Установите переменную окружения CHANNEL_ID."
            )
            return

        event = db.get_event_by_id(event_id)

        if not event:
            await query.answer("❌ Мероприятие не найдено или неактивно.")
            return

        title, description, event_date, attendee_limit, _ = event
        image_file_id = event[4] if len(event) > 4 else None

        # Create RSVP keyboard (no user_id for initial posting)
        reply_markup = create_rsvp_keyboard(event_id)

        # Format event card message with initial stats
        from utils.message_utils import format_event_card_message

        message = format_event_card_message(
            event_id, title, description, event_date, attendee_limit
        )

        try:
            # Post to the configured channel
            if image_file_id:
                await self.bot.application.bot.send_photo(
                    chat_id=config.CHANNEL_ID,
                    photo=image_file_id,
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
            else:
                await self.bot.application.bot.send_message(
                    chat_id=config.CHANNEL_ID,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )

            await query.answer(
                f"✅ Карточка мероприятия '{title}' опубликована в канале!"
            )

        except Exception as e:
            logger.error(
                f"Failed to post event card to channel {config.CHANNEL_ID}: {e}"
            )
            error_message = "❌ Ошибка при отправке в канал. "

            if "chat not found" in str(e).lower():
                error_message += f"Канал не найден (ID: {config.CHANNEL_ID}). Используйте /test_channel для диагностики."
            elif "not enough rights" in str(e).lower() or "forbidden" in str(e).lower():
                error_message += (
                    "Недостаточно прав. Добавьте бота как администратора канала."
                )
            else:
                error_message += (
                    f"Детали: {str(e)}. Используйте /test_channel для диагностики."
                )

            await query.answer(error_message)

    async def handle_save_and_post(self, query):
        """Handle saving changes and then posting the event card"""
        if not config.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[3])  # save_and_post_{event_id}
        user_id = query.from_user.id

        # First save the changes
        success = self._save_event_changes(user_id, event_id)

        if success:
            # Then post the card with the updated data
            await self._post_event_card(query, event_id)
            # Clear the edit data after successful save and post
            if user_id in self.bot.user_data:
                self.bot.user_data[user_id].clear()
        else:
            await query.edit_message_text("❌ Ошибка сохранения изменений.")

    async def handle_post_without_save(self, query):
        """Handle posting the event card without saving changes"""
        if not config.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[3])  # post_without_save_{event_id}

        # Post the card with current database data (without saving changes)
        await self._post_event_card(query, event_id)

        # Clear the edit data without saving
        user_id = query.from_user.id
        if user_id in self.bot.user_data:
            self.bot.user_data[user_id].clear()

    def _save_event_changes(self, user_id: int, event_id: int) -> bool:
        """Save event changes to database"""
        if user_id not in self.bot.user_data:
            logger.warning(f"User {user_id} not found in bot.user_data")
            return False

        user_data = self.bot.user_data[user_id]
        logger.info(f"Saving changes for user {user_id}, event {event_id}")
        logger.info(f"User data keys: {list(user_data.keys())}")

        if (
            not user_data.get("editing_event")
            or user_data.get("editing_event_id") != event_id
        ):
            logger.warning(f"User {user_id} is not editing event {event_id}")
            return False

        # Get the changes (only non-None values)
        title = user_data.get("event_title")
        event_date = user_data.get("event_date")
        description = user_data.get("event_description")
        attendee_limit = user_data.get("attendee_limit")
        image_file_id = user_data.get("event_image_file_id")

        # Check if there are any changes to save
        changes = {
            "title": title,
            "event_date": event_date,
            "description": description,
            "attendee_limit": attendee_limit,
            "image_file_id": image_file_id,
        }
        actual_changes = {k: v for k, v in changes.items() if v is not None}

        if not actual_changes:
            logger.warning(f"No changes to save for user {user_id}, event {event_id}")
            return False

        logger.info(f"Saving changes: {actual_changes}")

        # Update event in database
        success = db.update_event(
            event_id=event_id,
            title=title,
            description=description,
            event_date=event_date,
            attendee_limit=attendee_limit,
            image_file_id=image_file_id,
        )

        if success:
            logger.info(f"Successfully saved changes for event {event_id}")
        else:
            logger.error(f"Failed to save changes for event {event_id}")

        return success

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
        attending_users = db.get_attending_users(event_id)

        text = f"📊 *Статистика RSVP для '{event[0]}'*\n📅 Дата: {event[2]}\n\n"
        text += f"✅ иду: {stats['иду']}\n❌ не иду: {stats['не иду']}\n\n"
        text += "Всего ответов: " + str(stats["иду"] + stats["не иду"])

        if attending_users:
            text += f"\n\n👥 *Участники:*\n"
            # Format users with clear indication of contactability
            user_list = []

            for first_name, username, user_id in attending_users:
                display_name = escape_markdown(first_name)
                if username:
                    # Users with usernames can be contacted directly
                    user_list.append(f"[{display_name}](https://t.me/{username})")
                else:
                    # Users without usernames cannot be contacted until they start conversation with bot
                    user_list.append(f"{display_name} (ID: {user_id})")

            text += "\n".join(user_list)
            text += f"\n\n📝 *Примечание:* Пользователи без username должны сначала написать /start боту, чтобы получить уведомления."
        else:
            text += f"\n\n👥 *Участники:*\nПока нет подтверждений участия"

        from utils.keyboard_utils import create_back_to_admin_keyboard

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=create_back_to_admin_keyboard(),
        )

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

        from utils.keyboard_utils import create_back_to_admin_keyboard

        await query.edit_message_text(
            report,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=create_back_to_admin_keyboard(),
        )

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

        elif query.data == "create_limit":
            self.bot.user_data[user_id]["creating_event"] = True
            self.bot.user_data[user_id]["waiting_for"] = "attendee_limit"
            from utils.keyboard_utils import create_back_to_admin_keyboard

            await query.edit_message_text(
                "👥 Пожалуйста, введите лимит участников:\n\n"
                "Отправьте сообщение с числом участников (например: 50).\n\n"
                "Пример: 25\n\n"
                "💡 Введите число участников или отправьте 0 для снятия лимита.\n"
                "Если не хотите устанавливать лимит, нажмите '🔙 Назад в меню администратора'.",
                reply_markup=create_back_to_admin_keyboard(),
            )

        elif query.data == "create_image":
            self.bot.user_data[user_id]["creating_event"] = True
            self.bot.user_data[user_id]["waiting_for"] = "event_image"
            from utils.keyboard_utils import create_back_to_admin_keyboard

            await query.edit_message_text(
                "🖼️ Пожалуйста, прикрепите изображение:\n\n"
                "Отправьте сообщение с изображением, которое будет прикреплено к мероприятию.\n\n"
                "💡 Изображение будет отображаться в карточке мероприятия.\n"
                "Если не хотите прикреплять изображение, нажмите '🔙 Назад в меню администратора'.\n\n"
                "После прикрепления изображения вернитесь в меню создания мероприятия.",
                reply_markup=create_back_to_admin_keyboard(),
            )

        elif query.data == "remove_image":
            # Remove the attached image
            if (
                user_id in self.bot.user_data
                and "event_image_file_id" in self.bot.user_data[user_id]
            ):
                del self.bot.user_data[user_id]["event_image_file_id"]

            # Show updated status with new keyboard
            user_data = self.bot.user_data.get(user_id, {})
            status_text = format_event_creation_status(user_data)
            reply_markup = create_event_creation_keyboard(user_data)

            await query.edit_message_text(
                status_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )
            await query.answer("✅ Изображение удалено!")

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
        attendee_limit = user_data.get("attendee_limit")
        image_file_id = user_data.get("event_image_file_id")

        # Validate that we have at least a title
        if not title or title == "Без названия":
            await query.edit_message_text(
                "❌ Пожалуйста, сначала установите название мероприятия.\n\n"
                "Используйте кнопку '📝 Ввести название мероприятия' для установки названия."
            )
            return

        try:
            event_id = db.create_event(
                title, description, event_date, attendee_limit, image_file_id
            )

            # Clear the creation data
            if user_id in self.bot.user_data:
                self.bot.user_data[user_id].clear()

            # Format success message
            success_message = f"✅ Мероприятие успешно создано!\n\n"
            success_message += f"📝 Название: {title}\n"
            success_message += f"📅 Дата: {event_date}\n"
            success_message += f"📄 Описание: {description}\n"

            if attendee_limit is not None:
                success_message += f"👥 Лимит участников: {attendee_limit}\n"
            else:
                success_message += f"👥 Лимит участников: Не ограничен\n"

            if image_file_id:
                success_message += f"🖼️ Изображение: Прикреплено\n"

            success_message += f"\nID мероприятия: {event_id}"

            from utils.keyboard_utils import create_back_to_admin_keyboard

            await query.edit_message_text(
                success_message, reply_markup=create_back_to_admin_keyboard()
            )

        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка создания мероприятия: {str(e)}")

    async def clear_event_creation_data(self, query):
        """Clear event creation data for user"""
        user_id = query.from_user.id

        if user_id in self.bot.user_data:
            self.bot.user_data[user_id].clear()

        from utils.keyboard_utils import create_back_to_admin_keyboard

        await query.edit_message_text(
            "🗑️ Данные создания мероприятия очищены!\n\n"
            "Все поля сброшены. Вы можете начать заново создание мероприятия.",
            reply_markup=create_back_to_admin_keyboard(),
        )

    async def handle_edit_event_selection(self, query):
        """Handle event selection for editing"""
        if not config.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[2])
        event = db.get_event_by_id(event_id)

        if not event:
            await query.edit_message_text("❌ Мероприятие не найдено или неактивно.")
            return

        # Store the selected event for editing
        user_id = query.from_user.id
        if user_id not in self.bot.user_data:
            self.bot.user_data[user_id] = {}

        # Store original event data and mark as editing
        self.bot.user_data[user_id]["editing_event_id"] = event_id
        self.bot.user_data[user_id]["editing_event"] = True
        self.bot.user_data[user_id]["original_event"] = {
            "title": event[0],
            "description": event[1],
            "event_date": event[2],
            "attendee_limit": event[3],
            "image_file_id": event[4] if len(event) > 4 else None,
        }

        # Format current status with original data
        user_data = self.bot.user_data.get(user_id, {})
        status_text = format_event_edit_status(
            user_data, self.bot.user_data[user_id]["original_event"]
        )
        reply_markup = create_event_edit_keyboard(user_data)

        await query.edit_message_text(
            status_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
        )
        await query.answer("✅ Мероприятие выбрано для редактирования!")

    async def handle_event_edit_step(self, query):
        """Handle individual steps of event editing"""
        user_id = query.from_user.id

        # Check if user is admin
        if not config.is_admin(user_id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        # Initialize user_data if it doesn't exist
        if user_id not in self.bot.user_data:
            self.bot.user_data[user_id] = {}

        logger.info(f"Event edit step: {query.data} for user {user_id}")

        if query.data == "edit_title":
            logger.info(f"Setting up title edit for user {user_id}")
            self.bot.user_data[user_id]["waiting_for"] = "edit_title"
            await query.edit_message_text(
                "📝 Изменить название мероприятия:\n\n"
                "Отправьте сообщение с новым названием.\n\n"
                "Пример: Командная встреча\n\n"
                "💡 Просто введите название и отправьте как обычное сообщение."
            )

        elif query.data == "edit_date":
            self.bot.user_data[user_id]["waiting_for"] = "edit_date"
            await query.edit_message_text(
                "📅 Изменить дату мероприятия:\n\n"
                "Отправьте сообщение с новой датой в формате ГГГГ-ММ-ДД.\n\n"
                "Пример: 2024-12-25\n\n"
                "💡 Просто введите дату и отправьте как обычное сообщение."
            )

        elif query.data == "edit_description":
            self.bot.user_data[user_id]["waiting_for"] = "edit_description"
            await query.edit_message_text(
                "📄 Изменить описание мероприятия:\n\n"
                "Отправьте сообщение с новым описанием.\n\n"
                "Пример: Ежемесячная синхронизация команды\n\n"
                "💡 Просто введите описание и отправьте как обычное сообщение."
            )

        elif query.data == "edit_limit":
            self.bot.user_data[user_id]["waiting_for"] = "edit_attendee_limit"
            from utils.keyboard_utils import create_back_to_admin_keyboard

            await query.edit_message_text(
                "👥 Изменить лимит участников:\n\n"
                "Отправьте сообщение с новым числом участников (например: 50).\n\n"
                "Пример: 25\n\n"
                "💡 Введите число участников или отправьте 0 для снятия лимита.\n"
                "Если не хотите менять лимит, нажмите '🔙 Назад в меню администратора'.",
                reply_markup=create_back_to_admin_keyboard(),
            )

        elif query.data == "edit_image":
            self.bot.user_data[user_id]["waiting_for"] = "edit_event_image"
            from utils.keyboard_utils import create_back_to_admin_keyboard

            await query.edit_message_text(
                "🖼️ Изменить изображение:\n\n"
                "Отправьте сообщение с новым изображением, которое будет прикреплено к мероприятию.\n\n"
                "💡 Изображение будет отображаться в карточке мероприятия.\n"
                "Если не хотите менять изображение, нажмите '🔙 Назад в меню администратора'.\n\n"
                "После прикрепления изображения вернитесь в меню редактирования мероприятия.",
                reply_markup=create_back_to_admin_keyboard(),
            )

        elif query.data == "edit_remove_image":
            # Remove the attached image
            if (
                user_id in self.bot.user_data
                and "event_image_file_id" in self.bot.user_data[user_id]
            ):
                del self.bot.user_data[user_id]["event_image_file_id"]

            # Show updated status with new keyboard
            user_data = self.bot.user_data.get(user_id, {})
            original_event = self.bot.user_data.get(user_id, {}).get(
                "original_event", {}
            )
            status_text = format_event_edit_status(user_data, original_event)
            reply_markup = create_event_edit_keyboard(user_data)

            await query.edit_message_text(
                status_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )
            await query.answer("✅ Изображение удалено!")

        elif query.data == "edit_final":
            await self.save_event_edits(query)
        elif query.data == "edit_clear":
            await self.clear_event_edit_data(query)
        else:
            logger.warning(f"Неизвестный шаг редактирования мероприятия: {query.data}")
            await query.edit_message_text("❌ Неизвестное действие. Попробуйте снова.")

    async def save_event_edits(self, query):
        """Save event edits to database"""
        user_id = query.from_user.id

        # Get stored event data
        user_data = self.bot.user_data.get(user_id, {})
        event_id = user_data.get("editing_event_id")

        if not event_id:
            await query.edit_message_text(
                "❌ Ошибка: мероприятие для редактирования не найдено."
            )
            return

        # Get the changes (only non-None values)
        title = user_data.get("event_title")
        event_date = user_data.get("event_date")
        description = user_data.get("event_description")
        attendee_limit = user_data.get("attendee_limit")
        image_file_id = user_data.get("event_image_file_id")

        # Update event in database
        success = db.update_event(
            event_id=event_id,
            title=title,
            description=description,
            event_date=event_date,
            attendee_limit=attendee_limit,
            image_file_id=image_file_id,
        )

        if success:
            # Clear the edit data
            if user_id in self.bot.user_data:
                self.bot.user_data[user_id].clear()

            from utils.keyboard_utils import create_back_to_admin_keyboard

            await query.edit_message_text(
                "✅ Изменения успешно сохранены!\n\n"
                f"Мероприятие ID: {event_id} обновлено.",
                reply_markup=create_back_to_admin_keyboard(),
            )
        else:
            await query.edit_message_text("❌ Ошибка сохранения изменений.")

    async def clear_event_edit_data(self, query):
        """Clear event edit data for user"""
        user_id = query.from_user.id

        if user_id in self.bot.user_data:
            # Remove only edit-related data, keep original event data for display
            edit_keys = [
                key
                for key in self.bot.user_data[user_id].keys()
                if key.startswith(("event_", "waiting_for", "editing_"))
                and key != "original_event"
            ]
            for key in edit_keys:
                del self.bot.user_data[user_id][key]

        # Show updated status with cleared data
        user_data = self.bot.user_data.get(user_id, {})
        original_event = self.bot.user_data.get(user_id, {}).get("original_event", {})
        status_text = format_event_edit_status(user_data, original_event)
        from utils.keyboard_utils import create_back_to_admin_keyboard

        await query.edit_message_text(
            status_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=create_back_to_admin_keyboard(),
        )
