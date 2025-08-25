import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import config
from database import db
from utils.keyboard_utils import (
    create_admin_menu_keyboard,
    create_back_to_admin_keyboard,
    create_event_creation_keyboard,
    create_event_edit_selection_keyboard,
    create_event_selection_keyboard,
    create_notification_keyboard,
)
from utils.message_utils import (
    format_admin_events_list,
    format_event_creation_status,
    format_event_users_list,
    format_registrations_list,
    format_rsvp_stats,
    format_user_status_report,
)

logger = logging.getLogger(__name__)


class AdminHandlers:
    """Admin command and callback handlers"""

    def __init__(self, bot_instance):
        self.bot = bot_instance

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return config.is_admin(user_id)

    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin menu command handler"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text(
                "❌ Доступ запрещен. Только для администраторов."
            )
            return

        reply_markup = create_admin_menu_keyboard()
        await update.message.reply_text(
            "🔧 Панель администратора\nВыберите действие:", reply_markup=reply_markup
        )

    async def create_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create new event command - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "Использование: /create_event <название> <дата:ГГГГ-ММ-ДД> <описание>\n"
                "Пример: /create_event 'Командная встреча' 2024-12-25 'Ежемесячная синхронизация команды'\n\n"
                "💡 Совет: Прикрепите изображение к сообщению с командой, и оно будет добавлено к мероприятию!"
            )
            return

        title = context.args[0]
        event_date = context.args[1]
        description = " ".join(context.args[2:])

        # Check for attached image
        image_file_id = None
        if update.message.photo:
            # Get the highest resolution photo
            image_file_id = update.message.photo[-1].file_id

        try:
            # Validate date format
            datetime.strptime(event_date, "%Y-%m-%d")

            # Create event with optional image
            event_id = db.create_event(
                title, description, event_date, None, image_file_id
            )

            # Post event in the current chat with registration button
            await self._post_event_in_chat(
                update, event_id, title, description, event_date, image_file_id
            )

            success_message = f"✅ Мероприятие '{title}' успешно создано!"
            if image_file_id:
                success_message += "\n🖼️ Изображение прикреплено к мероприятию!"

            await update.message.reply_text(success_message)

        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка создания мероприятия: {str(e)}")

    async def _post_event_in_chat(
        self,
        update: Update,
        event_id: int,
        title: str,
        description: str,
        event_date: str,
        image_file_id: str = None,
    ):
        """Post event in the current chat with registration button"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Зарегистрироваться", callback_data=f"register_{event_id}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Get attendee limit and image for the event
        event = db.get_event_by_id(event_id)
        attendee_limit = event[3] if event and len(event) > 3 else None
        event_image_file_id = image_file_id or (
            event[4] if event and len(event) > 4 else None
        )

        # Format message with attendee limit info
        from utils.message_utils import format_simple_event_message

        message = format_simple_event_message(
            title, description, event_date, attendee_limit
        )

        # Send message with or without image
        if event_image_file_id:
            await update.message.reply_photo(
                photo=event_image_file_id,
                caption=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        else:
            await update.message.reply_text(
                text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )

    async def list_events(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all events - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        events = db.get_all_events()
        text = format_admin_events_list(events)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def event_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List users registered for specific event - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        if not context.args:
            await update.message.reply_text("Использование: /event_users <event_id>")
            return

        try:
            event_id = int(context.args[0])
            event = db.get_event_by_id(event_id)

            if not event:
                await update.message.reply_text("❌ Мероприятие не найдено.")
                return

            users = db.get_event_registrations(event_id)
            text = format_event_users_list(event[0], event[2], users)
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

        except ValueError:
            await update.message.reply_text("❌ Неверный ID мероприятия.")

    async def notify_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send notification to all registered users - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        if len(context.args) < 2:
            await update.message.reply_text(
                "Использование: /notify_users <event_id> <сообщение>"
            )
            return

        try:
            event_id = int(context.args[0])
            message = " ".join(context.args[1:])

            event = db.get_event_by_id(event_id)
            if not event:
                await update.message.reply_text("❌ Мероприятие не найдено.")
                return

            user_ids = db.get_registered_users_for_event(event_id)
            if not user_ids:
                await update.message.reply_text(
                    "❌ Нет зарегистрированных пользователей для этого мероприятия."
                )
                return

            # Send notifications
            notification_text = f"🔔 *Напоминание о мероприятии*\n\n📅 {event[0]} - {event[2]}\n\n{message}"

            sent_count = 0
            failed_count = 0
            blocked_users = []

            for user_id in user_ids:
                try:
                    await self.bot.application.bot.send_message(
                        chat_id=user_id,
                        text=notification_text,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    sent_count += 1
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Failed to send notification to user {user_id}: {e}")
                    failed_count += 1

                    if "bot can't initiate conversation" in error_msg.lower():
                        blocked_users.append(user_id)

            from utils.message_utils import format_notification_status

            status_message = format_notification_status(
                sent_count, len(user_ids), failed_count, blocked_users
            )
            await update.message.reply_text(status_message)

        except ValueError:
            await update.message.reply_text("❌ Неверный ID мероприятия.")

    async def post_event_card(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Post event card with RSVP buttons in chat group - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        if not context.args:
            await update.message.reply_text(
                "Использование: /post_event_card <event_id>"
            )
            return

        try:
            event_id = int(context.args[0])
            event = db.get_event_by_id(event_id)

            if not event:
                await update.message.reply_text(
                    "❌ Мероприятие не найдено или неактивно."
                )
                return

            title, description, event_date = event[:3]
            image_file_id = event[4] if len(event) > 4 else None

            # Create RSVP keyboard and message
            from utils.keyboard_utils import create_rsvp_keyboard
            from utils.message_utils import format_event_card_message

            reply_markup = create_rsvp_keyboard(event_id)
            message = format_event_card_message(
                event_id, title, description, event_date
            )

            # Send message with or without image
            if image_file_id:
                await update.message.reply_photo(
                    photo=image_file_id,
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
            else:
                await update.message.reply_text(
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )

        except ValueError:
            await update.message.reply_text("❌ Неверный ID мероприятия.")

    async def show_rsvp_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show RSVP statistics for a specific event - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        if not context.args:
            await update.message.reply_text("Использование: /rsvp_stats <event_id>")
            return

        try:
            event_id = int(context.args[0])
            event = db.get_event_by_id(event_id)

            if not event:
                await update.message.reply_text("❌ Мероприятие не найдено.")
                return

            stats = db.get_rsvp_stats(event_id)
            text = format_rsvp_stats(event[0], event[2], stats)
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

        except ValueError:
            await update.message.reply_text("❌ Неверный ID мероприятия.")

    async def check_user_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Check which users haven't started conversations with the bot - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        if not context.args:
            await update.message.reply_text("Использование: /check_users <event_id>")
            return

        try:
            event_id = int(context.args[0])
            event = db.get_event_by_id(event_id)

            if not event:
                await update.message.reply_text("❌ Мероприятие не найдено.")
                return

            # Get registered users and test message sending
            user_ids = db.get_registered_users_for_event(event_id)
            if not user_ids:
                await update.message.reply_text(
                    "❌ Нет зарегистрированных пользователей для этого мероприятия."
                )
                return

            test_message = "🔍 Это тестовое сообщение для проверки возможности получения уведомлений."
            reachable_users = []
            unreachable_users = []

            for user_id in user_ids:
                try:
                    await self.bot.application.bot.send_message(
                        chat_id=user_id, text=test_message
                    )
                    reachable_users.append(
                        (user_id, None, None)
                    )  # Simplified for this example
                except Exception as e:
                    error_msg = str(e)
                    if "bot can't initiate conversation" in error_msg.lower():
                        unreachable_users.append((user_id, None, None))

            report = format_user_status_report(
                event[0], event[2], reachable_users, unreachable_users
            )
            await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

        except ValueError:
            await update.message.reply_text("❌ Неверный ID мероприятия.")

    # Callback handlers for admin menu
    async def handle_admin_callback(self, query):
        """Handle admin callbacks"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        logger.info(f"Admin callback: {query.data} from user {query.from_user.id}")

        if query.data == "admin_create":
            await self.start_event_creation(query)
        elif query.data == "admin_edit":
            await self.show_edit_menu(query)
        elif query.data == "admin_list":
            await self.show_admin_events(query)
        elif query.data == "admin_registrations":
            await self.show_registrations(query)
        elif query.data == "admin_post_card":
            await self.show_post_card_menu(query)
        elif query.data == "admin_rsvp_stats":
            await self.show_rsvp_stats_menu(query)
        elif query.data == "admin_check_users":
            await self.show_check_users_menu(query)
        elif query.data == "admin_notify":
            await self.show_notify_menu(query)
        elif query.data == "admin_back":
            await self.handle_admin_back_with_auto_save(query)

    async def start_event_creation(self, query):
        """Start the event creation dialogue"""
        user_id = query.from_user.id
        user_data = self.bot.user_data.get(user_id, {})

        status_text = format_event_creation_status(user_data)
        reply_markup = create_event_creation_keyboard(user_data)

        await query.edit_message_text(
            status_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
        )

    async def show_admin_events(self, query):
        """Show events for admin"""
        events = db.get_all_events()
        text = format_admin_events_list(events)
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

    async def show_registrations(self, query):
        """Show registrations for admin"""
        events = db.get_events_with_registration_counts()
        text = format_registrations_list(events)
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

    async def show_post_card_menu(self, query):
        """Show menu for posting event cards"""
        events = db.get_active_events()
        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\n"
                "Сначала создайте мероприятие через панель администратора."
            )
            return

        # Extract event_id, title, event_date from events
        event_data = [(event[0], event[1], event[2]) for event in events]
        reply_markup = create_event_selection_keyboard(event_data, "post_card")

        await query.edit_message_text(
            "🎫 *Опубликовать карточку мероприятия*\n\n"
            "Выберите мероприятие для публикации RSVP карточки в этом чате:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

    async def show_rsvp_stats_menu(self, query):
        """Show menu for viewing RSVP statistics"""
        events = db.get_active_events()
        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\n"
                "Сначала создайте мероприятие через панель администратора."
            )
            return

        event_data = [(event[0], event[1], event[2]) for event in events]
        reply_markup = create_event_selection_keyboard(event_data, "view_stats")

        await query.edit_message_text(
            "📊 *Статистика RSVP*\n\n"
            "Выберите мероприятие для просмотра статистики RSVP:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

    async def show_check_users_menu(self, query):
        """Show menu for checking user status"""
        events = db.get_active_events()
        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\n"
                "Сначала создайте мероприятие через панель администратора."
            )
            return

        event_data = [(event[0], event[1], event[2]) for event in events]
        reply_markup = create_event_selection_keyboard(event_data, "check_users")

        await query.edit_message_text(
            "🔍 *Проверить статус пользователей*\n\n"
            "Выберите мероприятие для проверки, какие пользователи могут получать уведомления:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

    async def show_edit_menu(self, query):
        """Show event selection menu for editing"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        events = db.get_active_events()
        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\n"
                "Сначала создайте мероприятие через панель администратора."
            )
            return

        # Extract event_id, title, event_date from events
        event_data = [(event[0], event[1], event[2]) for event in events]
        reply_markup = create_event_edit_selection_keyboard(event_data)

        await query.edit_message_text(
            "✏️ *Редактирование мероприятия*\n\n"
            "Выберите мероприятие для редактирования:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

    async def show_notify_menu(self, query):
        """Show notification menu with event selection"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Access denied.")
            return

        events = db.get_active_events_for_notification()
        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\nСначала создайте мероприятие через меню администратора.",
                reply_markup=create_back_to_admin_keyboard(),
            )
            return

        reply_markup = create_notification_keyboard(events)

        await query.edit_message_text(
            "📢 *Отправить уведомления*\n\n"
            "Выберите мероприятие для отправки уведомлений зарегистрированным пользователям:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

    async def handle_admin_back_with_auto_save(self, query):
        """Handle admin back with auto-save functionality"""
        user_id = query.from_user.id

        # Check if user has unsaved changes and auto-save them
        if user_id in self.bot.user_data and self.bot.user_data[user_id].get(
            "editing_event"
        ):
            user_data = self.bot.user_data[user_id]
            event_id = user_data.get("editing_event_id")

            if event_id and self._has_unsaved_changes(user_id, event_id):
                # Auto-save the changes
                success = self._auto_save_event_changes(user_id, event_id)

                if success:
                    logger.info(
                        f"Auto-saved changes for event {event_id} by user {user_id}"
                    )
                    # Clear the edit data after successful auto-save
                    self.bot.user_data[user_id].clear()

                    # Show confirmation message briefly before showing admin menu
                    await query.answer("✅ Изменения автоматически сохранены!")

                    # Wait a moment before showing the admin menu
                    import asyncio

                    await asyncio.sleep(1)
                else:
                    logger.error(
                        f"Failed to auto-save changes for event {event_id} by user {user_id}"
                    )
                    await query.answer("⚠️ Не удалось автоматически сохранить изменения")

        # Show admin menu
        await self.admin_menu_from_callback(query)

    def _has_unsaved_changes(self, user_id: int, event_id: int) -> bool:
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

    def _auto_save_event_changes(self, user_id: int, event_id: int) -> bool:
        """Auto-save event changes to database"""
        if user_id not in self.bot.user_data:
            return False

        user_data = self.bot.user_data[user_id]

        if (
            not user_data.get("editing_event")
            or user_data.get("editing_event_id") != event_id
        ):
            return False

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

        return success

    async def admin_menu_from_callback(self, query):
        """Show admin menu from callback query"""
        reply_markup = create_admin_menu_keyboard()
        await query.edit_message_text(
            "🔧 Панель администратора\nВыберите действие:", reply_markup=reply_markup
        )
