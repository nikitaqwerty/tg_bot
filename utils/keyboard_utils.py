from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import db


def create_rsvp_keyboard(event_id: int, user_id: int = None) -> InlineKeyboardMarkup:
    """Create RSVP keyboard with user response indication"""
    stats = db.get_rsvp_stats(event_id)

    # Get user's current response if user_id is provided
    user_response = None
    if user_id:
        user_response = db.get_user_rsvp_response(event_id, user_id)

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


def create_event_list_keyboard(events: List[Tuple]) -> InlineKeyboardMarkup:
    """Create keyboard for event list"""
    keyboard = []
    for event_id, title, event_date, description in events:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{title} - {event_date}", callback_data=f"register_{event_id}"
                )
            ]
        )
    return InlineKeyboardMarkup(keyboard)


def create_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Create admin menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("📅 Создать мероприятие", callback_data="admin_create")],
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
                "🎫 Опубликовать карточку мероприятия", callback_data="admin_post_card"
            )
        ],
        [InlineKeyboardButton("📊 Статистика RSVP", callback_data="admin_rsvp_stats")],
        [
            InlineKeyboardButton(
                "🔍 Проверить статус пользователей", callback_data="admin_check_users"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_event_creation_keyboard(user_data: dict = None) -> InlineKeyboardMarkup:
    """Create event creation keyboard with dynamic image options"""
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
                "👥 Установить лимит участников", callback_data="create_limit"
            )
        ],
    ]

    # Add image-related buttons based on current state
    if user_data and user_data.get("event_image_file_id"):
        # Image is attached, show option to change or remove
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🖼️ Изменить изображение", callback_data="create_image"
                )
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🗑️ Удалить изображение", callback_data="remove_image"
                )
            ]
        )
    else:
        # No image attached, show option to attach
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🖼️ Прикрепить изображение", callback_data="create_image"
                )
            ]
        )

    keyboard.extend(
        [
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
    )

    return InlineKeyboardMarkup(keyboard)


def create_back_to_admin_keyboard() -> InlineKeyboardMarkup:
    """Create back to admin menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Назад в меню администратора", callback_data="admin_back"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_event_creation_continue_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for continuing event creation or returning to event creation menu"""
    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Продолжить создание мероприятия", callback_data="admin_create"
            )
        ],
        [InlineKeyboardButton("🏠 В меню администратора", callback_data="admin_back")],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_event_selection_keyboard(
    events: List[Tuple], callback_prefix: str
) -> InlineKeyboardMarkup:
    """Create keyboard for event selection with custom callback prefix"""
    keyboard = []
    for event_id, title, event_date in events:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{title} - {event_date}",
                    callback_data=f"{callback_prefix}_{event_id}",
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
    return InlineKeyboardMarkup(keyboard)


def create_notification_keyboard(events: List[Tuple]) -> InlineKeyboardMarkup:
    """Create keyboard for notification event selection"""
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
    return InlineKeyboardMarkup(keyboard)
