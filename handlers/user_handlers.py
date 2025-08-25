import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import db
from utils.keyboard_utils import create_event_list_keyboard

logger = logging.getLogger(__name__)


class UserHandlers:
    """User command handlers for public commands"""

    def __init__(self, bot_instance):
        self.bot = bot_instance

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        await update.message.reply_text(
            "Добро пожаловать в бота регистрации на мероприятия! 🎉\n\n"
            "Используйте /events для просмотра доступных мероприятий и регистрации.\n\n"
            "💡 *Важно:* Вам нужно начать разговор с этим ботом (отправив /start) "
            "чтобы получать уведомления и напоминания о мероприятиях!"
        )

    async def show_events(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available events"""
        events = db.get_active_events()

        if not events:
            await update.message.reply_text("Нет доступных активных мероприятий.")
            return

        reply_markup = create_event_list_keyboard(events)
        await update.message.reply_text(
            "📅 Доступные мероприятия:", reply_markup=reply_markup
        )
