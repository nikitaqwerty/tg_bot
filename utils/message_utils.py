from typing import List, Tuple

from database import db


def format_event_card_message(
    event_id: int,
    title: str,
    description: str,
    event_date: str,
    attendee_limit: int = None,
) -> str:
    """Format event card message"""
    message = f"🎉 *{escape_markdown(title)}*\n\n"
    if description:
        message += f"📝 {escape_markdown(description)}\n\n"
    message += f"📅 Дата: {event_date}\n\n"

    message += "Отметьтесь, пожалуйста:"
    return message


def format_event_creation_status(user_data: dict) -> str:
    """Format event creation status message"""
    title = user_data.get("event_title", "Не установлено")
    event_date = user_data.get("event_date", "Не установлено")
    description = user_data.get("event_description", "Не установлено")
    attendee_limit = user_data.get("attendee_limit")
    image_file_id = user_data.get("event_image_file_id")

    status_text = f"📝 *Создание мероприятия*\n\n"
    status_text += f"📝 Название: {escape_markdown(title)}\n"
    status_text += f"📅 Дата: {event_date}\n"
    status_text += f"📄 Описание: {escape_markdown(description)}\n"

    if attendee_limit is not None:
        status_text += f"👥 Лимит участников: {attendee_limit}\n"
    else:
        status_text += f"👥 Лимит участников: Не установлен\n"

    if image_file_id:
        status_text += f"🖼️ Изображение: Прикреплено\n"
    else:
        status_text += f"🖼️ Изображение: Не прикреплено\n"

    status_text += "\nНажмите кнопки ниже для ввода каждого поля:"

    return status_text


def format_event_edit_status(user_data: dict, original_event: dict) -> str:
    """Format event edit status message"""
    title = user_data.get("event_title", original_event.get("title", "Не установлено"))
    event_date = user_data.get(
        "event_date", original_event.get("event_date", "Не установлено")
    )
    description = user_data.get(
        "event_description", original_event.get("description", "Не установлено")
    )
    attendee_limit = user_data.get(
        "attendee_limit", original_event.get("attendee_limit")
    )
    image_file_id = user_data.get(
        "event_image_file_id", original_event.get("image_file_id")
    )

    status_text = f"✏️ *Редактирование мероприятия*\n\n"
    status_text += f"📝 Название: {escape_markdown(title)}\n"
    status_text += f"📅 Дата: {event_date}\n"
    status_text += f"📄 Описание: {escape_markdown(description)}\n"

    if attendee_limit is not None:
        status_text += f"👥 Лимит участников: {attendee_limit}\n"
    else:
        status_text += f"👥 Лимит участников: Не установлен\n"

    if image_file_id:
        status_text += f"🖼️ Изображение: Прикреплено\n"
    else:
        status_text += f"🖼️ Изображение: Не прикреплено\n"

    status_text += "\nНажмите кнопки ниже для изменения каждого поля:"

    return status_text


def format_admin_events_list(events: List[Tuple]) -> str:
    """Format admin events list message"""
    if not events:
        return "Мероприятия не найдены."

    text = "📅 *Все мероприятия:*\n\n"
    for event in events:
        if len(event) >= 6:  # New format with attendee_limit
            event_id, title, event_date, is_active, total_users, attendee_limit = event
        else:  # Old format without attendee_limit
            event_id, title, event_date, is_active, total_users = event
            attendee_limit = None

        status = "✅" if is_active else "❌"
        text += (
            f"{status} *{escape_markdown(title)}* (ID: {event_id})\n📅 {event_date}\n"
        )

        if attendee_limit:
            text += f"👥 {total_users}/{attendee_limit} зарегистрировано\n"
        else:
            text += f"👥 {total_users} зарегистрировано (без лимита)\n"

        text += "\n"

    return text


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters to prevent parsing errors"""
    special_chars = [
        "*",
        "_",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]
    escaped_text = text
    for char in special_chars:
        escaped_text = escaped_text.replace(char, f"\\{char}")
    return escaped_text


def format_registrations_list(events: List[Tuple]) -> str:
    """Format registrations list message"""
    if not events:
        return "Активные мероприятия не найдены."

    text = "👥 *Регистрации на мероприятия:*\n\n"
    for event in events:
        if len(event) >= 5:  # New format with attendee_limit
            event_id, title, event_date, total_users, attendee_limit = event
        else:  # Old format without attendee_limit
            event_id, title, event_date, total_users = event
            attendee_limit = None

        text += f"📅 *{escape_markdown(title)}* ({event_date})\n"

        if attendee_limit:
            text += f"👥 {total_users}/{attendee_limit} зарегистрировано\n"
        else:
            text += f"👥 {total_users} зарегистрировано (без лимита)\n"

        # Get attending usernames for this event
        from database import db

        attending_usernames = db.get_attending_usernames(event_id)

        if attending_usernames:
            # Escape special Markdown characters in usernames
            escaped_usernames = [
                escape_markdown(username) for username in attending_usernames
            ]
            text += f"✅ Участники: {', '.join(escaped_usernames)}\n"
        else:
            text += "✅ Участники: Пока нет подтверждений участия\n"

        text += "\n"

    return text


def format_event_users_list(
    event_title: str, event_date: str, users: List[Tuple]
) -> str:
    """Format event users list message"""
    text = f"👥 *Зарегистрированные пользователи для '{escape_markdown(event_title)}'*\n📅 Дата: {event_date}\n\n"

    if not users:
        text += "Пока нет зарегистрированных пользователей."
    else:
        for i, (username, first_name, registered_at, source) in enumerate(users, 1):
            name = escape_markdown(first_name or "Неизвестно")
            username_text = (
                f"@{escape_markdown(username)}" if username else "Без username"
            )
            source_emoji = "📝" if source == "registration" else "✅"
            text += f"{i}. {name} ({username_text}) {source_emoji}\n"

    return text


def format_rsvp_stats(event_title: str, event_date: str, stats: dict) -> str:
    """Format RSVP statistics message"""
    text = f"📊 *Статистика RSVP для '{escape_markdown(event_title)}'*\n📅 Дата: {event_date}\n\n"
    text += f"✅ иду: {stats['иду']}\n❌ не иду: {stats['не иду']}\n\n"
    text += "Всего ответов: " + str(stats["иду"] + stats["не иду"])
    return text


def format_user_status_report(
    event_title: str,
    event_date: str,
    reachable_users: List[Tuple],
    unreachable_users: List[Tuple],
) -> str:
    """Format user status report message"""
    report = f"📊 *Отчет о статусе пользователей*\n\n"
    report += f"📅 Мероприятие: {escape_markdown(event_title)}\n"
    report += f"📅 Дата: {event_date}\n\n"
    report += f"✅ *Доступные пользователи ({len(reachable_users)}):*\n"

    for user_id, username, first_name in reachable_users:
        display_name = username or first_name or f"Пользователь {user_id}"
        report += f"• {escape_markdown(display_name)}\n"

    if unreachable_users:
        report += f"\n❌ *Недоступные пользователи ({len(unreachable_users)}):*\n"
        report += f"*Эти пользователи должны сначала отправить /start боту:*\n"

        for user_id, username, first_name in unreachable_users:
            display_name = username or first_name or f"Пользователь {user_id}"
            report += f"• {escape_markdown(display_name)}\n"

    return report


def format_notification_status(
    sent_count: int, total_count: int, failed_count: int, blocked_users: List[int]
) -> str:
    """Format notification status message"""
    status_message = (
        f"✅ Уведомления отправлены {sent_count}/{total_count} пользователям."
    )

    if failed_count > 0:
        status_message += f"\n❌ Не удалось отправить {failed_count} пользователям."
        if blocked_users:
            status_message += (
                f"\n\n⚠️ {len(blocked_users)} пользователей не начали общение с ботом."
            )
            status_message += (
                "\nИм нужно сначала отправить /start боту, чтобы получать уведомления."
            )

    return status_message


def format_simple_event_message(
    title: str, description: str, event_date: str, attendee_limit: int = None
) -> str:
    """Format simple event message without RSVP stats"""
    message = f"🎉 *{escape_markdown(title)}*\n\n"
    if description:
        message += f"📝 {escape_markdown(description)}\n\n"
    message += f"📅 Дата: {event_date}\n"

    if attendee_limit:
        # Get current registration count
        from database import db

        # We need event_id to get the count, but for simple messages we might not have it
        # For now, just show the limit
        message += f"👥 Лимит участников: {attendee_limit}\n\n"
    else:
        message += "\n"

    message += "Нажмите ниже для регистрации!"
    return message
