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
            "Welcome to Event Registration Bot! 🎉\n\n"
            "Use /events to see available events and register.\n\n"
            "💡 *Important:* You need to start a conversation with this bot (by sending /start) "
            "to receive event notifications and reminders!"
        )

    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin menu"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied. Admin only.")
            return

        keyboard = [
            [InlineKeyboardButton("📅 Create Event", callback_data="admin_create")],
            [InlineKeyboardButton("📋 List Events", callback_data="admin_list")],
            [
                InlineKeyboardButton(
                    "👥 View Registrations", callback_data="admin_registrations"
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Send Notifications", callback_data="admin_notify"
                )
            ],
            [
                InlineKeyboardButton(
                    "🎫 Post Event Card", callback_data="admin_post_card"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 View RSVP Stats", callback_data="admin_rsvp_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔍 Check User Status", callback_data="admin_check_users"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔍 Check User Status", callback_data="admin_check_users"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔧 Admin Panel\nSelect an action:", reply_markup=reply_markup
        )

    async def create_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create new event - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: /create_event <title> <date:YYYY-MM-DD> <description>\n"
                "Example: /create_event 'Team Meeting' 2024-12-25 'Monthly team sync'"
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

            await update.message.reply_text(f"✅ Event '{title}' created successfully!")

        except ValueError:
            await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD")
        except Exception as e:
            await update.message.reply_text(f"❌ Error creating event: {str(e)}")

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
            [InlineKeyboardButton("📝 Register", callback_data=f"register_{event_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = f"🎉 *{title}*\n\n📅 Date: {event_date}\n📝 {description}\n\nClick below to register!"

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
            await update.message.reply_text("No active events available.")
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
            "📅 Available Events:", reply_markup=reply_markup
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
            logger.warning(f"Unknown callback data: {query.data}")

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
                "💡 Tip: Use /admin to access the admin panel and create events."
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
                f"Unexpected input state for user {user_id}: waiting_for={waiting_for}"
            )
            await update.message.reply_text(
                "❌ Unexpected input. Please use /admin to access the creation menu."
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
                    "❌ Error: No event selected. Please try again."
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
                f"Unexpected notification input state for user {user_id}: waiting_for={waiting_for}"
            )
            await update.message.reply_text(
                "❌ Unexpected input. Please use /admin to access the notification menu."
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
            await query.edit_message_text("❌ Event not found.")
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
            f"✅ Successfully registered for '{event[0]}' on {event[1]}!\n"
            "You'll receive a notification before the event."
        )

    async def handle_rsvp_response(self, query):
        """Handle RSVP responses"""
        parts = query.data.split("_")
        if len(parts) < 3:
            logger.warning(f"Invalid RSVP callback data: {query.data}")
            await query.answer("Invalid RSVP response.")
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
            await query.answer("❌ Access denied.")
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
            await query.answer("❌ Event not found or inactive.")
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

        await query.answer("✅ Event card posted!")

    async def handle_view_stats_selection(self, query):
        """Handle event selection for viewing RSVP statistics"""
        if not self.is_admin(query.from_user.id):
            await query.answer("❌ Access denied.")
            return

        event_id = int(query.data.split("_")[2])

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        cursor.execute("SELECT title, event_date FROM events WHERE id = ?", (event_id,))
        event = cursor.fetchone()
        conn.close()

        if not event:
            await query.answer("❌ Event not found.")
            return

        stats = await self.get_rsvp_stats(event_id)

        text = f"📊 *RSVP Statistics for '{event[0]}'*\n📅 Date: {event[1]}\n\n"
        text += f"✅ иду: {stats['иду']}\n❌ не иду: {stats['не иду']}\n\n"
        text += "Total RSVPs: " + str(stats["иду"] + stats["не иду"])

        await query.edit_message_text(text, parse_mode="Markdown")

    async def handle_check_users_selection(self, query):
        """Handle event selection for checking user status"""
        if not self.is_admin(query.from_user.id):
            await query.answer("❌ Access denied.")
            return

        event_id = int(query.data.split("_")[2])

        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()

        # Get event details
        cursor.execute("SELECT title, event_date FROM events WHERE id = ?", (event_id,))
        event = cursor.fetchone()

        if not event:
            await query.answer("❌ Event not found.")
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
            await query.edit_message_text("❌ No users registered for this event.")
            return

        # Test sending a message to each user
        test_message = (
            "🔍 This is a test message to check if you can receive notifications."
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
        report = f"📊 *User Status Report*\n\n"
        report += f"📅 Event: {event[0]}\n"
        report += f"📅 Date: {event[1]}\n\n"
        report += f"✅ *Reachable Users ({len(reachable_users)}):*\n"

        for user_id, username, first_name in reachable_users:
            display_name = username or first_name or f"User {user_id}"
            report += f"• {display_name}\n"

        if unreachable_users:
            report += f"\n❌ *Unreachable Users ({len(unreachable_users)}):*\n"
            report += f"*These users need to send /start to the bot first:*\n"

            for user_id, username, first_name in unreachable_users:
                display_name = username or first_name or f"User {user_id}"
                report += f"• {display_name}\n"

        await query.edit_message_text(report, parse_mode="Markdown")

    async def handle_admin_callback(self, query):
        """Handle admin callbacks"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Access denied.")
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

        title = user_data.get("event_title", "Not set")
        event_date = user_data.get("event_date", "Not set")
        description = user_data.get("event_description", "Not set")

        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Enter Event Title", callback_data="create_title"
                )
            ],
            [InlineKeyboardButton("📅 Enter Event Date", callback_data="create_date")],
            [
                InlineKeyboardButton(
                    "📄 Enter Description", callback_data="create_description"
                )
            ],
            [InlineKeyboardButton("✅ Create Event", callback_data="create_final")],
            [InlineKeyboardButton("🗑️ Clear Data", callback_data="create_clear")],
            [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        status_text = f"📝 *Event Creation*\n\n"
        status_text += f"📝 Title: {title}\n"
        status_text += f"📅 Date: {event_date}\n"
        status_text += f"📄 Description: {description}\n\n"
        status_text += "Click the buttons below to enter each field:"

        await query.edit_message_text(
            status_text, parse_mode="Markdown", reply_markup=reply_markup
        )

    async def handle_event_creation_step(self, query):
        """Handle individual steps of event creation"""
        user_id = query.from_user.id

        # Check if user is admin
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Access denied.")
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
                "📝 Please enter the event title:\n\n"
                "Send a message with the title.\n\n"
                "Example: Team Meeting\n\n"
                "💡 Just type the title and send it as a regular message."
            )

        elif query.data == "create_date":
            self.user_data[user_id]["creating_event"] = True
            self.user_data[user_id]["waiting_for"] = "date"
            await query.edit_message_text(
                "📅 Please enter the event date:\n\n"
                "Send a message with the date in YYYY-MM-DD format.\n\n"
                "Example: 2024-12-25\n\n"
                "💡 Just type the date and send it as a regular message."
            )

        elif query.data == "create_description":
            self.user_data[user_id]["creating_event"] = True
            self.user_data[user_id]["waiting_for"] = "description"
            await query.edit_message_text(
                "📄 Please enter the event description:\n\n"
                "Send a message with the description.\n\n"
                "Example: Monthly team sync meeting\n\n"
                "💡 Just type the description and send it as a regular message."
            )

        elif query.data == "create_final":
            await self.create_event_from_dialogue(query)
        elif query.data == "create_clear":
            await self.clear_event_creation_data(query)
        else:
            logger.warning(f"Unknown event creation step: {query.data}")
            await query.edit_message_text("❌ Unknown action. Please try again.")

    async def create_event_from_dialogue(self, query):
        """Create event using the dialogue data"""
        user_id = query.from_user.id

        # Get stored event data
        user_data = self.user_data.get(user_id, {})

        title = user_data.get("event_title", "Untitled Event")
        event_date = user_data.get("event_date", datetime.now().strftime("%Y-%m-%d"))
        description = user_data.get("event_description", "No description provided")

        # Validate that we have at least a title
        if not title or title == "Untitled Event":
            await query.edit_message_text(
                "❌ Please set an event title first.\n\n"
                "Use the '📝 Enter Event Title' button to set the title."
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
                f"✅ Event created successfully!\n\n"
                f"📝 Title: {title}\n"
                f"📅 Date: {event_date}\n"
                f"📄 Description: {description}\n\n"
                f"Event ID: {event_id}"
            )

        except Exception as e:
            await query.edit_message_text(f"❌ Error creating event: {str(e)}")

    async def clear_event_creation_data(self, query):
        """Clear event creation data for user"""
        user_id = query.from_user.id

        if user_id in self.user_data:
            self.user_data[user_id].clear()

        await query.edit_message_text(
            "🗑️ Event creation data cleared!\n\n"
            "All fields have been reset. You can start over with event creation."
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
                "❌ No active events found.\n\n"
                "Create an event first using the admin panel."
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
            [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back")]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🎫 *Post Event Card*\n\n"
            "Select an event to post an RSVP card in this chat:",
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
                "❌ No active events found.\n\n"
                "Create an event first using the admin panel."
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
            [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back")]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📊 *RSVP Statistics*\n\n" "Select an event to view RSVP statistics:",
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
                "❌ No active events found.\n\n"
                "Create an event first using the admin panel."
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
            [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back")]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔍 *Check User Status*\n\n"
            "Select an event to check which users can receive notifications:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def admin_menu_from_callback(self, query):
        """Show admin menu from callback query"""
        keyboard = [
            [InlineKeyboardButton("📅 Create Event", callback_data="admin_create")],
            [InlineKeyboardButton("📋 List Events", callback_data="admin_list")],
            [
                InlineKeyboardButton(
                    "👥 View Registrations", callback_data="admin_registrations"
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Send Notifications", callback_data="admin_notify"
                )
            ],
            [
                InlineKeyboardButton(
                    "🎫 Post Event Card", callback_data="admin_post_card"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 View RSVP Stats", callback_data="admin_rsvp_stats"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔧 Admin Panel\nSelect an action:", reply_markup=reply_markup
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
            await query.edit_message_text("No events found.")
            return

        text = "📅 *All Events:*\n\n"
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
            await query.edit_message_text("No active events found.")
            return

        text = "👥 *Event Registrations:*\n\n"
        for title, event_date, total_users in events:
            text += f"📅 *{title}* ({event_date})\n👤 {total_users} registered\n\n"

        await query.edit_message_text(text, parse_mode="Markdown")

    async def event_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List users registered for specific event - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return

        if not context.args:
            await update.message.reply_text("Usage: /event_users <event_id>")
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
                await update.message.reply_text("❌ Event not found.")
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

            text = f"👥 *Registered Users for '{event[0]}'*\n📅 Date: {event[1]}\n\n"

            if not users:
                text += "No users registered yet."
            else:
                for i, (username, first_name, registered_at, source) in enumerate(
                    users, 1
                ):
                    name = first_name or "Unknown"
                    username_text = f"@{username}" if username else "No username"
                    source_emoji = "📝" if source == "registration" else "✅"
                    text += f"{i}. {name} ({username_text}) {source_emoji}\n"

            await update.message.reply_text(text, parse_mode="Markdown")

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

    async def notify_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send notification to all registered users - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("Usage: /notify_users <event_id> <message>")
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
                await update.message.reply_text("❌ Event not found.")
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
                    "❌ No users registered for this event."
                )
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

            status_message = (
                f"✅ Notifications sent to {sent_count}/{len(user_ids)} users."
            )
            if failed_count > 0:
                status_message += f"\n❌ Failed to send to {failed_count} users."
                if blocked_users:
                    status_message += f"\n\n⚠️ {len(blocked_users)} users haven't started a conversation with the bot."
                    status_message += "\nThey need to send /start to the bot first to receive notifications."

            await update.message.reply_text(status_message)

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

    async def post_event_card(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Post event card with RSVP buttons in chat group - Admin only"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return

        if not context.args:
            await update.message.reply_text("Usage: /post_event_card <event_id>")
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
                await update.message.reply_text("❌ Event not found or inactive.")
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
            await update.message.reply_text("❌ Access denied.")
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
            await update.message.reply_text("No events found.")
            return

        text = "📅 *All Events:*\n\n"
        for event_id, title, event_date, is_active, total_users in events:
            status = "✅" if is_active else "❌"
            text += f"{status} *{title}* (ID: {event_id})\n📅 {event_date}\n👤 {total_users} registered\n\n"

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
                "❌ No active events found.\n\nCreate an event first using the admin menu.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Back to Admin Menu", callback_data="admin_back"
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
                        f"📅 {title} ({total_users} users)",
                        callback_data=f"notify_event_{event_id}",
                    )
                ]
            )

        keyboard.append(
            [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back")]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📢 *Send Notifications*\n\n"
            "Select an event to send notifications to registered users:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def handle_notify_event_selection(self, query):
        """Handle event selection for notifications"""
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Access denied.")
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
            await query.edit_message_text("❌ Event not found.")
            return

        await query.edit_message_text(
            f"📢 *Send Notification*\n\n"
            f"📅 Event: {event[0]}\n"
            f"📅 Date: {event[1]}\n\n"
            f"Please send the notification message:\n\n"
            f'💡 Example: "Don\'t forget to bring your laptop!"\n\n'
            f"Just type your message and send it as a regular message.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Event Selection", callback_data="admin_notify"
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
            await update.message.reply_text("❌ Access denied.")
            return

        if not context.args:
            await update.message.reply_text("Usage: /check_users <event_id>")
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
                await update.message.reply_text("❌ Event not found.")
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
                    "❌ No users registered for this event."
                )
                return

            # Test sending a message to each user
            test_message = (
                "🔍 This is a test message to check if you can receive notifications."
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
            report = f"📊 *User Status Report*\n\n"
            report += f"📅 Event: {event[0]}\n"
            report += f"📅 Date: {event[1]}\n\n"
            report += f"✅ *Reachable Users ({len(reachable_users)}):*\n"

            for user_id, username, first_name in reachable_users:
                display_name = username or first_name or f"User {user_id}"
                report += f"• {display_name}\n"

            if unreachable_users:
                report += f"\n❌ *Unreachable Users ({len(unreachable_users)}):*\n"
                report += f"*These users need to send /start to the bot first:*\n"

                for user_id, username, first_name in unreachable_users:
                    display_name = username or first_name or f"User {user_id}"
                    report += f"• {display_name}\n"

            await update.message.reply_text(report, parse_mode="Markdown")

        except ValueError:
            await update.message.reply_text("❌ Invalid event ID.")

    def run(self):
        """Run the bot"""
        print("Starting Event Registration Bot...")
        self.application.run_polling()


# Configuration
if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()

    # Environment variables
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

    if not all([BOT_TOKEN, ADMIN_IDS]):
        print("❌ Please set BOT_TOKEN and ADMIN_IDS environment variables")
        exit(1)

    # Create and run bot
    bot = EventBot(BOT_TOKEN, ADMIN_IDS)
    bot.run()
