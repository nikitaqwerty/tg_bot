import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List

import pytz
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    filters,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Database setup
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect("events.db")
    cursor = conn.cursor()

    # Events table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    """
    )

    # Registrations table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            registered_at TEXT,
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(event_id, user_id)
        )
    """
    )

    # RSVP table for event cards
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rsvp_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            response TEXT CHECK(response IN ('иду', 'не иду')),
            responded_at TEXT,
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(event_id, user_id)
        )
    """
    )

    conn.commit()
    conn.close()


class EventBot:
    def __init__(self, token: str, admin_ids: List[int]):
        self.token = token
        self.admin_ids = admin_ids
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
        self.user_data = {}  # Store user data for event creation
        init_db()

    def setup_handlers(self):
        """Setup command and callback handlers"""
        # Admin commands
        self.application.add_handler(CommandHandler("admin", self.admin_menu))
        self.application.add_handler(CommandHandler("create_event", self.create_event))
        self.application.add_handler(CommandHandler("list_events", self.list_events))
        self.application.add_handler(CommandHandler("event_users", self.event_users))
        self.application.add_handler(CommandHandler("notify_users", self.notify_users))
        self.application.add_handler(
            CommandHandler("post_event_card", self.post_event_card)
        )
        self.application.add_handler(CommandHandler("rsvp_stats", self.show_rsvp_stats))
        self.application.add_handler(
            CommandHandler("check_users", self.check_user_status)
        )

        # Public commands
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("events", self.show_events))

        # Message handler for event creation input
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.admin_ids

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        await update.message.reply_text(
            "Добро пожаловать в бота регистрации на мероприятия! 🎉\n\n"
            "Используйте /events для просмотра доступных мероприятий и регистрации.\n\n"
            "💡 *Важно:* Вам нужно начать разговор с этим ботом (отправив /start) "
            "чтобы получать уведомления и напоминания о мероприятиях!"
        )

    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin menu"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text(
                "❌ Доступ запрещен. Только для администраторов."
            )
            return

        keyboard = [
            [
                InlineKeyboardButton(
                    "📅 Создать мероприятие", callback_data="admin_create"
                )
            ],
            [InlineKeyboardButton("📋 Список мероприятий", callback_data="admin_list")],
            [
                InlineKeyboardButton(
                    "👥 Просмотр регистраций", callback_data="admin_registrations"
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Отправить уведомления", callback_data="admin_notify"
                )
            ],
            [
                InlineKeyboardButton(
                    "🎫 Опубликовать карточку мероприятия",
                    callback_data="admin_post_card",
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Статистика RSVP", callback_data="admin_rsvp_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔍 Проверить статус пользователей",
                    callback_data="admin_check_users",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔍 Проверить статус пользователей",
                    callback_data="admin_check_users",
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔧 Панель администратора\nВыберите действие:", reply_markup=reply_markup
        )

    async def create_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create new event - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "Использование: /create_event <название> <дата:ГГГГ-ММ-ДД> <описание>\n"
                "Пример: /create_event 'Командная встреча' 2024-12-25 'Ежемесячная синхронизация команды'"
            )
            return

        title = context.args[0]
        event_date = context.args[1]
        description = " ".join(context.args[2:])

        try:
            # Validate date format
            datetime.strptime(event_date, "%Y-%m-%d")

            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (title, description, event_date, created_at) VALUES (?, ?, ?, ?)",
                (title, description, event_date, datetime.now().isoformat()),
            )
            event_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # Post event in the current chat with registration button
            await self.post_event_in_chat(
                update, event_id, title, description, event_date
            )

            await update.message.reply_text(
                f"✅ Мероприятие '{title}' успешно создано!"
            )

        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка создания мероприятия: {str(e)}")

    async def post_event_in_chat(
        self,
        update: Update,
        event_id: int,
        title: str,
        description: str,
        event_date: str,
    ):
        """Post event in the current chat with registration button"""
        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Зарегистрироваться", callback_data=f"register_{event_id}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = f"🎉 *{title}*\n\n📅 Дата: {event_date}\n📝 {description}\n\nНажмите ниже для регистрации!"

        await update.message.reply_text(
            text=message, parse_mode="Markdown", reply_markup=reply_markup
        )

    async def show_events(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available events"""
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, event_date, description FROM events WHERE is_active = 1"
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await update.message.reply_text("Нет доступных активных мероприятий.")
            return

        keyboard = []
        for event_id, title, event_date, description in events:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{title} - {event_date}", callback_data=f"register_{event_id}"
                    )
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📅 Доступные мероприятия:", reply_markup=reply_markup
        )

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

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages for event creation"""
        user_id = update.effective_user.id

        # Log all incoming messages for debugging
        logger.info(f"Received message from user {user_id}: {update.message.text}")

        if not self.is_admin(user_id):
            logger.info(f"User {user_id} is not admin, ignoring message")
            return

        # Check if user is in event creation mode
        if user_id in self.user_data and self.user_data[user_id].get("creating_event"):
            logger.info(
                f"Processing event creation input from user {user_id}: {update.message.text}"
            )
            await self.handle_event_creation_input(update, user_id)
        # Check if user is in notification creation mode
        elif user_id in self.user_data and self.user_data[user_id].get(
            "creating_notification"
        ):
            logger.info(
                f"Processing notification input from user {user_id}: {update.message.text}"
            )
            await self.handle_notification_input(update, user_id)
        else:
            logger.info(
                f"User {user_id} not in event creation mode. User data: {self.user_data.get(user_id, 'Not found')}"
            )
            # Provide helpful feedback to admin users
            await update.message.reply_text(
                "💡 Совет: Используйте /admin для доступа к панели администратора и создания мероприятий."
            )

    async def handle_event_creation_input(self, update: Update, user_id: int):
        """Handle user input during event creation"""
        user_input = update.message.text
        waiting_for = self.user_data[user_id].get("waiting_for")

        logger.info(
            f"Handling event creation input for user {user_id}, waiting_for: {waiting_for}, input: {user_input}"
        )

        if waiting_for == "title":
            logger.info(f"Setting title for user {user_id}: {user_input}")
            self.user_data[user_id]["event_title"] = user_input
            self.user_data[user_id]["waiting_for"] = None
            self.user_data[user_id]["creating_event"] = False  # Clear creation mode
            await update.message.reply_text(
                f"✅ Title set: {user_input}\n\n"
                "Use /admin to return to the creation menu and continue with other fields."
            )

        elif waiting_for == "date":
            try:
                # Validate date format
                datetime.strptime(user_input, "%Y-%m-%d")
                self.user_data[user_id]["event_date"] = user_input
                self.user_data[user_id]["waiting_for"] = None
                self.user_data[user_id]["creating_event"] = False  # Clear creation mode
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
            self.user_data[user_id]["event_description"] = user_input
            self.user_data[user_id]["waiting_for"] = None
            self.user_data[user_id]["creating_event"] = False  # Clear creation mode
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
        waiting_for = self.user_data[user_id].get("waiting_for")

        logger.info(
            f"Handling notification input for user {user_id}, waiting_for: {waiting_for}, input: {user_input}"
        )

        if waiting_for == "notification_message":
            event_id = self.user_data[user_id].get("notify_event_id")

            if not event_id:
                await update.message.reply_text(
                    "❌ Ошибка: Мероприятие не выбрано. Попробуйте снова."
                )
                self.user_data[user_id]["creating_notification"] = False
                self.user_data[user_id]["waiting_for"] = None
                return

            # Send the notification
            await self.send_notification_to_event_users(event_id, user_input, update)

            # Clear the notification creation state
            self.user_data[user_id]["creating_notification"] = False
            self.user_data[user_id]["waiting_for"] = None
            self.user_data[user_id]["notify_event_id"] = None
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
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()

        # Get event details
        cursor.execute("SELECT title, event_date FROM events WHERE id = ?", (event_id,))
        event = cursor.fetchone()

        if not event:
            await update.message.reply_text("❌ Event not found.")
            conn.close()
            return

        # Get registered users from both tables
        cursor.execute(
            """
            SELECT DISTINCT user_id FROM registrations WHERE event_id = ?
            UNION
            SELECT DISTINCT user_id FROM rsvp_responses WHERE event_id = ?
            """,
            (event_id, event_id),
        )
        user_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not user_ids:
            await update.message.reply_text("❌ No users registered for this event.")
            return

        # Send notifications
        notification_text = (
            f"🔔 *Event Reminder*\n\n📅 {event[0]} - {event[1]}\n\n{message}"
        )

        sent_count = 0
        failed_count = 0
        blocked_users = []

        for user_id in user_ids:
            try:
                await self.application.bot.send_message(
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
        status_message = f"✅ Notifications sent to {sent_count}/{len(user_ids)} users."
        if failed_count > 0:
            status_message += f"\n❌ Failed to send to {failed_count} users."
            if blocked_users:
                status_message += f"\n\n⚠️ {len(blocked_users)} users haven't started a conversation with the bot."
                status_message += "\nThey need to send /start to the bot first to receive notifications."

        await update.message.reply_text(status_message)

    async def handle_registration(self, query):
        """Handle event registration"""
        event_id = int(query.data.split("_")[1])
        user = query.from_user

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()

        # Check if already registered
        cursor.execute(
            "SELECT id FROM registrations WHERE event_id = ? AND user_id = ?",
            (event_id, user.id),
        )
        if cursor.fetchone():
            await query.edit_message_text(
                "✅ You're already registered for this event!"
            )
            conn.close()
            return

        # Get event details
        cursor.execute("SELECT title, event_date FROM events WHERE id = ?", (event_id,))
        event = cursor.fetchone()

        if not event:
            await query.edit_message_text("❌ Мероприятие не найдено.")
            conn.close()
            return

        # Register user
        cursor.execute(
            "INSERT INTO registrations (event_id, user_id, username, first_name, registered_at) VALUES (?, ?, ?, ?, ?)",
            (
                event_id,
                user.id,
                user.username,
                user.first_name,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        await query.edit_message_text(
            f"✅ Успешно зарегистрированы на '{event[0]}' {event[1]}!\n"
            "Вы получите уведомление перед мероприятием."
        )

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

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()

        # Get event details first
        cursor.execute(
            "SELECT title, description, event_date FROM events WHERE id = ?",
            (event_id,),
        )
        event = cursor.fetchone()

        if not event:
            await query.answer("❌ Event not found.")
            conn.close()
            return

        # Check if user has already responded and get their previous response
        cursor.execute(
            "SELECT response FROM rsvp_responses WHERE event_id = ? AND user_id = ?",
            (event_id, user.id),
        )
        existing_response = cursor.fetchone()
        previous_response = existing_response[0] if existing_response else None

        # Update or insert the response (allow changing responses)
        if existing_response:
            # Update existing response
            cursor.execute(
                "UPDATE rsvp_responses SET response = ?, responded_at = ? WHERE event_id = ? AND user_id = ?",
                (response, datetime.now().isoformat(), event_id, user.id),
            )
            action_message = f"✅ Изменен ответ: {previous_response} → {response}"
        else:
            # Insert new response
            cursor.execute(
                "INSERT INTO rsvp_responses (event_id, user_id, username, first_name, response, responded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    user.id,
                    user.username,
                    user.first_name,
                    response,
                    datetime.now().isoformat(),
                ),
            )
            action_message = f"✅ Ваш ответ: {response}"

        conn.commit()

        # Get updated RSVP statistics and responses
        stats = await self.get_rsvp_stats(event_id)

        # Get recent responses (last 5)
        cursor.execute(
            """
            SELECT first_name, username, response 
            FROM rsvp_responses 
            WHERE event_id = ? 
            ORDER BY responded_at DESC 
            LIMIT 5
            """,
            (event_id,),
        )
        recent_responses = cursor.fetchall()
        conn.close()

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
        reply_markup = await self.create_rsvp_keyboard(event_id, user.id)

        # Update the message
        try:
            await query.edit_message_text(
                text=message, parse_mode="Markdown", reply_markup=reply_markup
            )
            await query.answer(action_message)
        except Exception as e:
            logger.error(f"Error updating RSVP message: {e}")
            await query.answer(action_message)

    async def get_rsvp_stats(self, event_id: int) -> Dict[str, int]:
        """Get RSVP statistics for an event"""
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT response, COUNT(*) FROM rsvp_responses WHERE event_id = ? GROUP BY response",
            (event_id,),
        )
        results = cursor.fetchall()
        conn.close()

        stats = {"иду": 0, "не иду": 0}
        for response, count in results:
            stats[response] = count

        return stats

    async def create_rsvp_keyboard(
        self, event_id: int, user_id: int = None
    ) -> InlineKeyboardMarkup:
        """Create RSVP keyboard with user response indication"""
        stats = await self.get_rsvp_stats(event_id)

        # Get user's current response if user_id is provided
        user_response = None
        if user_id:
            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response FROM rsvp_responses WHERE event_id = ? AND user_id = ?",
                (event_id, user_id),
            )
            user_current_response = cursor.fetchone()
            user_response = user_current_response[0] if user_current_response else None
            conn.close()

        keyboard = [
            [
                InlineKeyboardButton(
                    f"✅ иду ({stats['иду']}){' ← Вы' if user_response == 'иду' else ''}",
                    callback_data=f"rsvp_{event_id}_иду",
                ),
                InlineKeyboardButton(
                    f"❌ не иду ({stats['не иду']}){' ← Вы' if user_response == 'не иду' else ''}",
                    callback_data=f"rsvp_{event_id}_не иду",
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def handle_post_card_selection(self, query):
        """Handle event selection for posting event card"""
        if not self.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[2])

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT title, description, event_date FROM events WHERE id = ? AND is_active = 1",
            (event_id,),
        )
        event = cursor.fetchall()
        conn.close()

        if not event:
            await query.answer("❌ Мероприятие не найдено или неактивно.")
            return

        title, description, event_date = event[0]

        # Create RSVP keyboard (no user_id for initial posting)
        reply_markup = await self.create_rsvp_keyboard(event_id)

        # Get current RSVP statistics for message
        stats = await self.get_rsvp_stats(event_id)

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
            text=message, parse_mode="Markdown", reply_markup=reply_markup
        )

        await query.answer("✅ Карточка мероприятия опубликована!")

    async def handle_view_stats_selection(self, query):
        """Handle event selection for viewing RSVP statistics"""
        if not self.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[2])

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute("SELECT title, event_date FROM events WHERE id = ?", (event_id,))
        event = cursor.fetchone()
        conn.close()

        if not event:
            await query.answer("❌ Мероприятие не найдено.")
            return

        stats = await self.get_rsvp_stats(event_id)

        text = f"📊 *Статистика RSVP для '{event[0]}'*\n📅 Дата: {event[1]}\n\n"
        text += f"✅ иду: {stats['иду']}\n❌ не иду: {stats['не иду']}\n\n"
        text += "Всего ответов: " + str(stats["иду"] + stats["не иду"])

        await query.edit_message_text(text, parse_mode="Markdown")

    async def handle_check_users_selection(self, query):
        """Handle event selection for checking user status"""
        if not self.is_admin(query.from_user.id):
            await query.answer("❌ Доступ запрещен.")
            return

        event_id = int(query.data.split("_")[2])

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()

        # Get event details
        cursor.execute("SELECT title, event_date FROM events WHERE id = ?", (event_id,))
        event = cursor.fetchone()

        if not event:
            await query.answer("❌ Мероприятие не найдено.")
            conn.close()
            return

        # Get all registered users for this event
        cursor.execute(
            "SELECT user_id, username, first_name FROM registrations WHERE event_id = ?",
            (event_id,),
        )
        registered_users = cursor.fetchall()
        conn.close()

        if not registered_users:
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

        for user_id, username, first_name in registered_users:
            try:
                await self.application.bot.send_message(
                    chat_id=user_id, text=test_message
                )
                reachable_users.append((user_id, username, first_name))
            except Exception as e:
                error_msg = str(e)
                if "bot can't initiate conversation" in error_msg.lower():
                    unreachable_users.append((user_id, username, first_name))

        # Create status report
        report = f"📊 *Отчет о статусе пользователей*\n\n"
        report += f"📅 Мероприятие: {event[0]}\n"
        report += f"📅 Дата: {event[1]}\n\n"
        report += f"✅ *Доступные пользователи ({len(reachable_users)}):*\n"

        for user_id, username, first_name in reachable_users:
            display_name = username or first_name or f"Пользователь {user_id}"
            report += f"• {display_name}\n"

        if unreachable_users:
            report += f"\n❌ *Недоступные пользователи ({len(unreachable_users)}):*\n"
            report += f"*Эти пользователи должны сначала отправить /start боту:*\n"

            for user_id, username, first_name in unreachable_users:
                display_name = username or first_name or f"Пользователь {user_id}"
                report += f"• {display_name}\n"

        await query.edit_message_text(report, parse_mode="Markdown")

    async def handle_admin_callback(self, query):
        """Handle admin callbacks"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        logger.info(f"Admin callback: {query.data} from user {query.from_user.id}")

        if query.data == "admin_create":
            await self.start_event_creation(query)
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
            await self.admin_menu_from_callback(query)

    async def start_event_creation(self, query):
        """Start the event creation dialogue"""
        user_id = query.from_user.id

        # Get current event data
        user_data = self.user_data.get(user_id, {})

        title = user_data.get("event_title", "Не установлено")
        event_date = user_data.get("event_date", "Не установлено")
        description = user_data.get("event_description", "Не установлено")

        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Ввести название мероприятия", callback_data="create_title"
                )
            ],
            [
                InlineKeyboardButton(
                    "📅 Ввести дату мероприятия", callback_data="create_date"
                )
            ],
            [
                InlineKeyboardButton(
                    "📄 Ввести описание", callback_data="create_description"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Создать мероприятие", callback_data="create_final"
                )
            ],
            [InlineKeyboardButton("🗑️ Очистить данные", callback_data="create_clear")],
            [
                InlineKeyboardButton(
                    "🔙 Назад в меню администратора", callback_data="admin_back"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        status_text = f"📝 *Создание мероприятия*\n\n"
        status_text += f"📝 Название: {title}\n"
        status_text += f"📅 Дата: {event_date}\n"
        status_text += f"📄 Описание: {description}\n\n"
        status_text += "Нажмите кнопки ниже для ввода каждого поля:"

        await query.edit_message_text(
            status_text, parse_mode="Markdown", reply_markup=reply_markup
        )

    async def handle_event_creation_step(self, query):
        """Handle individual steps of event creation"""
        user_id = query.from_user.id

        # Check if user is admin
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        # Initialize user_data if it doesn't exist
        if user_id not in self.user_data:
            self.user_data[user_id] = {}

        logger.info(f"Event creation step: {query.data} for user {user_id}")

        if query.data == "create_title":
            logger.info(f"Setting up title input for user {user_id}")
            self.user_data[user_id]["creating_event"] = True
            self.user_data[user_id]["waiting_for"] = "title"
            logger.info(f"User data for {user_id}: {self.user_data[user_id]}")
            await query.edit_message_text(
                "📝 Пожалуйста, введите название мероприятия:\n\n"
                "Отправьте сообщение с названием.\n\n"
                "Пример: Командная встреча\n\n"
                "💡 Просто введите название и отправьте как обычное сообщение."
            )

        elif query.data == "create_date":
            self.user_data[user_id]["creating_event"] = True
            self.user_data[user_id]["waiting_for"] = "date"
            await query.edit_message_text(
                "📅 Пожалуйста, введите дату мероприятия:\n\n"
                "Отправьте сообщение с датой в формате ГГГГ-ММ-ДД.\n\n"
                "Пример: 2024-12-25\n\n"
                "💡 Просто введите дату и отправьте как обычное сообщение."
            )

        elif query.data == "create_description":
            self.user_data[user_id]["creating_event"] = True
            self.user_data[user_id]["waiting_for"] = "description"
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
        user_data = self.user_data.get(user_id, {})

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
            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (title, description, event_date, created_at) VALUES (?, ?, ?, ?)",
                (title, description, event_date, datetime.now().isoformat()),
            )
            event_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # Clear the creation data
            if user_id in self.user_data:
                self.user_data[user_id].clear()

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

        if user_id in self.user_data:
            self.user_data[user_id].clear()

        await query.edit_message_text(
            "🗑️ Данные создания мероприятия очищены!\n\n"
            "Все поля сброшены. Вы можете начать заново создание мероприятия."
        )

    async def show_post_card_menu(self, query):
        """Show menu for posting event cards"""
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, event_date FROM events WHERE is_active = 1 ORDER BY event_date"
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\n"
                "Сначала создайте мероприятие через панель администратора."
            )
            return

        keyboard = []
        for event_id, title, event_date in events:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{title} - {event_date}", callback_data=f"post_card_{event_id}"
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔙 Назад в меню администратора", callback_data="admin_back"
                )
            ]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🎫 *Опубликовать карточку мероприятия*\n\n"
            "Выберите мероприятие для публикации RSVP карточки в этом чате:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def show_rsvp_stats_menu(self, query):
        """Show menu for viewing RSVP statistics"""
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, event_date FROM events WHERE is_active = 1 ORDER BY event_date"
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\n"
                "Сначала создайте мероприятие через панель администратора."
            )
            return

        keyboard = []
        for event_id, title, event_date in events:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{title} - {event_date}",
                        callback_data=f"view_stats_{event_id}",
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔙 Назад в меню администратора", callback_data="admin_back"
                )
            ]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📊 *Статистика RSVP*\n\n"
            "Выберите мероприятие для просмотра статистики RSVP:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def show_check_users_menu(self, query):
        """Show menu for checking user status"""
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, event_date FROM events WHERE is_active = 1 ORDER BY event_date"
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\n"
                "Сначала создайте мероприятие через панель администратора."
            )
            return

        keyboard = []
        for event_id, title, event_date in events:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{title} - {event_date}",
                        callback_data=f"check_users_{event_id}",
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔙 Назад в меню администратора", callback_data="admin_back"
                )
            ]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔍 *Проверить статус пользователей*\n\n"
            "Выберите мероприятие для проверки, какие пользователи могут получать уведомления:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def admin_menu_from_callback(self, query):
        """Show admin menu from callback query"""
        keyboard = [
            [
                InlineKeyboardButton(
                    "📅 Создать мероприятие", callback_data="admin_create"
                )
            ],
            [InlineKeyboardButton("📋 Список мероприятий", callback_data="admin_list")],
            [
                InlineKeyboardButton(
                    "👥 Просмотр регистраций", callback_data="admin_registrations"
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Отправить уведомления", callback_data="admin_notify"
                )
            ],
            [
                InlineKeyboardButton(
                    "🎫 Опубликовать карточку мероприятия",
                    callback_data="admin_post_card",
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Статистика RSVP", callback_data="admin_rsvp_stats"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔧 Панель администратора\nВыберите действие:", reply_markup=reply_markup
        )

    async def show_admin_events(self, query):
        """Show events for admin"""
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, event_date, is_active FROM events ORDER BY event_date"
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await query.edit_message_text("Мероприятия не найдены.")
            return

        text = "📅 *Все мероприятия:*\n\n"
        for event_id, title, event_date, is_active in events:
            status = "✅" if is_active else "❌"
            text += f"{status} *{title}* - {event_date} (ID: {event_id})\n"

        await query.edit_message_text(text, parse_mode="Markdown")

    async def show_registrations(self, query):
        """Show registrations for admin"""
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.title, e.event_date, 
                   (COUNT(DISTINCT r.user_id) + COUNT(DISTINCT rs.user_id)) as total_users
            FROM events e
            LEFT JOIN registrations r ON e.id = r.event_id
            LEFT JOIN rsvp_responses rs ON e.id = rs.event_id
            WHERE e.is_active = 1
            GROUP BY e.id, e.title, e.event_date
            ORDER BY e.event_date
        """
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await query.edit_message_text("Активные мероприятия не найдены.")
            return

        text = "👥 *Регистрации на мероприятия:*\n\n"
        for title, event_date, total_users in events:
            text += (
                f"📅 *{title}* ({event_date})\n👤 {total_users} зарегистрировано\n\n"
            )

        await query.edit_message_text(text, parse_mode="Markdown")

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

            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT e.title, e.event_date FROM events WHERE id = ?", (event_id,)
            )
            event = cursor.fetchone()

            if not event:
                await update.message.reply_text("❌ Мероприятие не найдено.")
                conn.close()
                return

            cursor.execute(
                """
                SELECT username, first_name, registered_at, 'registration' as source
                FROM registrations 
                WHERE event_id = ?
                UNION ALL
                SELECT username, first_name, responded_at as registered_at, 'rsvp' as source
                FROM rsvp_responses 
                WHERE event_id = ?
                ORDER BY registered_at
            """,
                (event_id, event_id),
            )
            users = cursor.fetchall()
            conn.close()

            text = f"👥 *Зарегистрированные пользователи для '{event[0]}'*\n📅 Дата: {event[1]}\n\n"

            if not users:
                text += "Пока нет зарегистрированных пользователей."
            else:
                for i, (username, first_name, registered_at, source) in enumerate(
                    users, 1
                ):
                    name = first_name or "Неизвестно"
                    username_text = f"@{username}" if username else "Без username"
                    source_emoji = "📝" if source == "registration" else "✅"
                    text += f"{i}. {name} ({username_text}) {source_emoji}\n"

            await update.message.reply_text(text, parse_mode="Markdown")

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

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

            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()

            # Get event details
            cursor.execute(
                "SELECT title, event_date FROM events WHERE id = ?", (event_id,)
            )
            event = cursor.fetchone()

            if not event:
                await update.message.reply_text("❌ Мероприятие не найдено.")
                conn.close()
                return

            # Get registered users
            cursor.execute(
                "SELECT DISTINCT user_id FROM registrations WHERE event_id = ?",
                (event_id,),
            )
            user_ids = [row[0] for row in cursor.fetchall()]
            conn.close()

            if not user_ids:
                await update.message.reply_text(
                    "❌ Нет зарегистрированных пользователей для этого мероприятия."
                )
                return

            # Send notifications
            notification_text = f"🔔 *Напоминание о мероприятии*\n\n📅 {event[0]} - {event[1]}\n\n{message}"

            sent_count = 0
            failed_count = 0
            blocked_users = []

            for user_id in user_ids:
                try:
                    await self.application.bot.send_message(
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

            status_message = (
                f"✅ Уведомления отправлены {sent_count}/{len(user_ids)} пользователям."
            )
            if failed_count > 0:
                status_message += (
                    f"\n❌ Не удалось отправить {failed_count} пользователям."
                )
                if blocked_users:
                    status_message += f"\n\n⚠️ {len(blocked_users)} пользователей не начали разговор с ботом."
                    status_message += "\nИм нужно сначала отправить /start боту для получения уведомлений."

            await update.message.reply_text(status_message)

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

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

            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, description, event_date FROM events WHERE id = ? AND is_active = 1",
                (event_id,),
            )
            event = cursor.fetchall()
            conn.close()

            if not event:
                await update.message.reply_text(
                    "❌ Мероприятие не найдено или неактивно."
                )
                return

            title, description, event_date = event[0]

            # Create RSVP keyboard (no user_id for initial posting)
            reply_markup = await self.create_rsvp_keyboard(event_id)

            # Get current RSVP statistics for message
            stats = await self.get_rsvp_stats(event_id)

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

            # Post the event card
            await update.message.reply_text(
                text=message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

    async def show_rsvp_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show RSVP statistics for a specific event - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return

        if not context.args:
            await update.message.reply_text("Usage: /rsvp_stats <event_id>")
            return

        try:
            event_id = int(context.args[0])

            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, event_date FROM events WHERE id = ?", (event_id,)
            )
            event = cursor.fetchone()
            conn.close()

            if not event:
                await update.message.reply_text("❌ Event not found.")
                return

            stats = await self.get_rsvp_stats(event_id)

            text = f"📊 *RSVP Statistics for '{event[0]}'*\n📅 Date: {event[1]}\n\n"
            text += f"✅ иду: {stats['иду']}\n❌ не иду: {stats['не иду']}\n\n"
            text += "Total RSVPs: " + str(stats["иду"] + stats["не иду"])

            await update.message.reply_text(text, parse_mode="Markdown")

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

    async def list_events(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all events - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен.")
            return

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.id, e.title, e.event_date, e.is_active, 
                   (COUNT(DISTINCT r.user_id) + COUNT(DISTINCT rs.user_id)) as total_users
            FROM events e
            LEFT JOIN registrations r ON e.id = r.event_id
            LEFT JOIN rsvp_responses rs ON e.id = rs.event_id
            GROUP BY e.id, e.title, e.event_date, e.is_active
            ORDER BY e.event_date DESC
        """
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await update.message.reply_text("Мероприятия не найдены.")
            return

        text = "📅 *Все мероприятия:*\n\n"
        for event_id, title, event_date, is_active, total_users in events:
            status = "✅" if is_active else "❌"
            text += f"{status} *{title}* (ID: {event_id})\n📅 {event_date}\n👤 {total_users} зарегистрировано\n\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    async def show_rsvp_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show RSVP statistics for a specific event - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return

        if not context.args:
            await update.message.reply_text("Usage: /rsvp_stats <event_id>")
            return

        try:
            event_id = int(context.args[0])

            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, event_date FROM events WHERE id = ?", (event_id,)
            )
            event = cursor.fetchone()
            conn.close()

            if not event:
                await update.message.reply_text("❌ Event not found.")
                return

            stats = await self.get_rsvp_stats(event_id)

            text = f"📊 *RSVP Statistics for '{event[0]}'*\n📅 Date: {event[1]}\n\n"
            text += f"✅ иду: {stats['иду']}\n❌ не иду: {stats['не иду']}\n\n"
            text += "Total RSVPs: " + str(stats["иду"] + stats["не иду"])

            await update.message.reply_text(text, parse_mode="Markdown")

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

    async def show_notify_menu(self, query):
        """Show notification menu with event selection"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Access denied.")
            return

        # Get active events
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.id, e.title, e.event_date, 
                   (COUNT(DISTINCT r.user_id) + COUNT(DISTINCT rs.user_id)) as total_users
            FROM events e
            LEFT JOIN registrations r ON e.id = r.event_id
            LEFT JOIN rsvp_responses rs ON e.id = rs.event_id
            WHERE e.is_active = 1
            GROUP BY e.id, e.title, e.event_date
            ORDER BY e.event_date DESC
        """
        )
        events = cursor.fetchall()
        conn.close()

        if not events:
            await query.edit_message_text(
                "❌ Активные мероприятия не найдены.\n\nСначала создайте мероприятие через меню администратора.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Назад в меню администратора",
                                callback_data="admin_back",
                            )
                        ]
                    ]
                ),
            )
            return

        # Create keyboard with events
        keyboard = []
        for event_id, title, event_date, total_users in events:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"📅 {title} ({total_users} пользователей)",
                        callback_data=f"notify_event_{event_id}",
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔙 Назад в меню администратора", callback_data="admin_back"
                )
            ]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📢 *Отправить уведомления*\n\n"
            "Выберите мероприятие для отправки уведомлений зарегистрированным пользователям:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def handle_notify_event_selection(self, query):
        """Handle event selection for notifications"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Доступ запрещен.")
            return

        # Extract event_id from callback data
        event_id = int(query.data.split("_")[2])

        # Store the selected event_id for the notification
        user_id = query.from_user.id
        if user_id not in self.user_data:
            self.user_data[user_id] = {}

        self.user_data[user_id]["notify_event_id"] = event_id
        self.user_data[user_id]["waiting_for"] = "notification_message"
        self.user_data[user_id]["creating_notification"] = True

        # Get event details
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute("SELECT title, event_date FROM events WHERE id = ?", (event_id,))
        event = cursor.fetchone()
        conn.close()

        if not event:
            await query.edit_message_text("❌ Мероприятие не найдено.")
            return

        await query.edit_message_text(
            f"📢 *Отправить уведомление*\n\n"
            f"📅 Мероприятие: {event[0]}\n"
            f"📅 Дата: {event[1]}\n\n"
            f"Пожалуйста, отправьте сообщение уведомления:\n\n"
            f'💡 Пример: "Не забудьте взять ноутбук!"\n\n'
            f"Просто введите ваше сообщение и отправьте как обычное сообщение.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Назад к выбору мероприятия",
                            callback_data="admin_notify",
                        )
                    ]
                ]
            ),
        )

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

            conn = sqlite3.connect("events.db")
            cursor = conn.cursor()

            # Get event details
            cursor.execute(
                "SELECT title, event_date FROM events WHERE id = ?", (event_id,)
            )
            event = cursor.fetchone()

            if not event:
                await update.message.reply_text("❌ Мероприятие не найдено.")
                conn.close()
                return

            # Get all registered users for this event
            cursor.execute(
                "SELECT user_id, username, first_name FROM registrations WHERE event_id = ?",
                (event_id,),
            )
            registered_users = cursor.fetchall()
            conn.close()

            if not registered_users:
                await update.message.reply_text(
                    "❌ Нет зарегистрированных пользователей для этого мероприятия."
                )
                return

            # Test sending a message to each user
            test_message = "🔍 Это тестовое сообщение для проверки возможности получения уведомлений."
            reachable_users = []
            unreachable_users = []

            for user_id, username, first_name in registered_users:
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id, text=test_message
                    )
                    reachable_users.append((user_id, username, first_name))
                except Exception as e:
                    error_msg = str(e)
                    if "bot can't initiate conversation" in error_msg.lower():
                        unreachable_users.append((user_id, username, first_name))

            # Create status report
            report = f"📊 *Отчет о статусе пользователей*\n\n"
            report += f"📅 Мероприятие: {event[0]}\n"
            report += f"📅 Дата: {event[1]}\n\n"
            report += f"✅ *Доступные пользователи ({len(reachable_users)}):*\n"

            for user_id, username, first_name in reachable_users:
                display_name = username or first_name or f"Пользователь {user_id}"
                report += f"• {display_name}\n"

            if unreachable_users:
                report += (
                    f"\n❌ *Недоступные пользователи ({len(unreachable_users)}):*\n"
                )
                report += f"*Эти пользователи должны сначала отправить /start боту:*\n"

                for user_id, username, first_name in unreachable_users:
                    display_name = username or first_name or f"Пользователь {user_id}"
                    report += f"• {display_name}\n"

            await update.message.reply_text(report, parse_mode="Markdown")

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

    def run(self):
        """Run the bot"""
        print("Запуск бота регистрации на мероприятия...")
        self.application.run_polling()


# Configuration
if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()

    # Environment variables
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

    if not all([BOT_TOKEN, ADMIN_IDS]):
        print("❌ Пожалуйста, установите переменные окружения BOT_TOKEN и ADMIN_IDS")
        exit(1)

    # Create and run bot
    bot = EventBot(BOT_TOKEN, ADMIN_IDS)
    bot.run()
