from typing import List, Tuple

from database import db


def format_event_card_message(
    event_id: int, title: str, description: str, event_date: str
) -> str:
    """Format event card message with RSVP statistics"""
    stats = db.get_rsvp_stats(event_id)
    recent_responses = db.get_recent_rsvp_responses(event_id)

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
    return message


def format_event_creation_status(user_data: dict) -> str:
    """Format event creation status message"""
    title = user_data.get("event_title", "Не установлено")
    event_date = user_data.get("event_date", "Не установлено")
    description = user_data.get("event_description", "Не установлено")

    status_text = f"📝 *Создание мероприятия*\n\n"
    status_text += f"📝 Название: {title}\n"
    status_text += f"📅 Дата: {event_date}\n"
    status_text += f"📄 Описание: {description}\n\n"
    status_text += "Нажмите кнопки ниже для ввода каждого поля:"

    return status_text


def format_admin_events_list(events: List[Tuple]) -> str:
    """Format admin events list message"""
    if not events:
        return "Мероприятия не найдены."

    text = "📅 *Все мероприятия:*\n\n"
    for event_id, title, event_date, is_active, total_users in events:
        status = "✅" if is_active else "❌"
        text += f"{status} *{title}* (ID: {event_id})\n📅 {event_date}\n👤 {total_users} зарегистрировано\n\n"

    return text


def format_registrations_list(events: List[Tuple]) -> str:
    """Format registrations list message"""
    if not events:
        return "Активные мероприятия не найдены."

    text = "👥 *Регистрации на мероприятия:*\n\n"
    for title, event_date, total_users in events:
        text += f"📅 *{title}* ({event_date})\n👤 {total_users} зарегистрировано\n\n"

    return text


def format_event_users_list(
    event_title: str, event_date: str, users: List[Tuple]
) -> str:
    """Format event users list message"""
    text = f"👥 *Зарегистрированные пользователи для '{event_title}'*\n📅 Дата: {event_date}\n\n"

    if not users:
        text += "Пока нет зарегистрированных пользователей."
    else:
        for i, (username, first_name, registered_at, source) in enumerate(users, 1):
            name = first_name or "Неизвестно"
            username_text = f"@{username}" if username else "Без username"
            source_emoji = "📝" if source == "registration" else "✅"
            text += f"{i}. {name} ({username_text}) {source_emoji}\n"

    return text


def format_rsvp_stats(event_title: str, event_date: str, stats: dict) -> str:
    """Format RSVP statistics message"""
    text = f"📊 *Статистика RSVP для '{event_title}'*\n📅 Дата: {event_date}\n\n"
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
    report += f"📅 Мероприятие: {event_title}\n"
    report += f"📅 Дата: {event_date}\n\n"
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

    return report


def format_notification_status(
    sent_count: int, total_count: int, failed_count: int, blocked_users: List[int]
) -> str:
    """Format notification status message"""
    status_message = f"✅ Notifications sent to {sent_count}/{total_count} users."

    if failed_count > 0:
        status_message += f"\n❌ Failed to send to {failed_count} users."
        if blocked_users:
            status_message += f"\n\n⚠️ {len(blocked_users)} users haven't started a conversation with the bot."
            status_message += (
                "\nThey need to send /start to the bot first to receive notifications."
            )

    return status_message


def format_simple_event_message(title: str, description: str, event_date: str) -> str:
    """Format simple event message without RSVP stats"""
    message = f"🎉 *{title}*\n\n"
    if description:
        message += f"📝 {description}\n\n"
    message += f"📅 Дата: {event_date}\n\n"
    message += "Нажмите ниже для регистрации!"
    return message
