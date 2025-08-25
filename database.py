import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database operations for the Telegram Event Bot"""

    def __init__(self, database_path: str = "events.db"):
        self.database_path = database_path
        self.init_db()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.database_path)
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """Initialize SQLite database with required tables"""
        with self.get_connection() as conn:
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
                    is_active BOOLEAN DEFAULT 1,
                    attendee_limit INTEGER,
                    image_file_id TEXT
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

            # Add missing columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE events ADD COLUMN attendee_limit INTEGER")
            except sqlite3.OperationalError:
                # Column already exists
                pass

            try:
                cursor.execute("ALTER TABLE events ADD COLUMN image_file_id TEXT")
            except sqlite3.OperationalError:
                # Column already exists
                pass

            conn.commit()

    def create_event(
        self,
        title: str,
        description: str,
        event_date: str,
        attendee_limit: int = None,
        image_file_id: str = None,
    ) -> int:
        """Create a new event and return its ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (title, description, event_date, created_at, attendee_limit, image_file_id) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    title,
                    description,
                    event_date,
                    datetime.now().isoformat(),
                    attendee_limit,
                    image_file_id,
                ),
            )
            event_id = cursor.lastrowid
            conn.commit()
            return event_id

    def update_event(
        self,
        event_id: int,
        title: str = None,
        description: str = None,
        event_date: str = None,
        attendee_limit: int = None,
        image_file_id: str = None,
    ) -> bool:
        """Update an existing event. Only non-None values will be updated"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Build the update query dynamically based on provided values
            update_fields = []
            values = []

            if title is not None:
                update_fields.append("title = ?")
                values.append(title)
            if description is not None:
                update_fields.append("description = ?")
                values.append(description)
            if event_date is not None:
                update_fields.append("event_date = ?")
                values.append(event_date)
            if attendee_limit is not None:
                update_fields.append("attendee_limit = ?")
                values.append(attendee_limit)
            if image_file_id is not None:
                update_fields.append("image_file_id = ?")
                values.append(image_file_id)

            if not update_fields:
                return False  # Nothing to update

            # Add event_id to values
            values.append(event_id)

            query = f"UPDATE events SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()

            return cursor.rowcount > 0

    def get_active_events(self) -> List[Tuple]:
        """Get all active events"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, event_date, description, attendee_limit, image_file_id FROM events WHERE is_active = 1"
            )
            return cursor.fetchall()

    def get_all_events(self) -> List[Tuple]:
        """Get all events with registration counts"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT e.id, e.title, e.event_date, e.is_active,
                       (COUNT(DISTINCT r.user_id) + COUNT(DISTINCT rs.user_id)) as total_users,
                       e.attendee_limit
                FROM events e
                LEFT JOIN registrations r ON e.id = r.event_id
                LEFT JOIN rsvp_responses rs ON e.id = rs.event_id
                GROUP BY e.id, e.title, e.event_date, e.is_active, e.attendee_limit
                ORDER BY e.event_date DESC
            """
            )
            return cursor.fetchall()

    def get_event_by_id(self, event_id: int) -> Optional[Tuple]:
        """Get event by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, description, event_date, attendee_limit, image_file_id FROM events WHERE id = ?",
                (event_id,),
            )
            return cursor.fetchone()

    def register_user_for_event(
        self, event_id: int, user_id: int, username: str, first_name: str
    ) -> bool:
        """Register a user for an event"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO registrations (event_id, user_id, username, first_name, registered_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        event_id,
                        user_id,
                        username,
                        first_name,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # User already registered
            return False

    def is_user_registered(self, event_id: int, user_id: int) -> bool:
        """Check if user is registered for an event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM registrations WHERE event_id = ? AND user_id = ?",
                (event_id, user_id),
            )
            return cursor.fetchone() is not None

    def get_event_registrations(self, event_id: int) -> List[Tuple]:
        """Get all registrations for an event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
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
            return cursor.fetchall()

    def get_registered_users_for_event(self, event_id: int) -> List[int]:
        """Get all user IDs registered for an event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT user_id FROM registrations WHERE event_id = ?
                UNION
                SELECT DISTINCT user_id FROM rsvp_responses WHERE event_id = ?
            """,
                (event_id, event_id),
            )
            return [row[0] for row in cursor.fetchall()]

    def get_registration_count(self, event_id: int) -> int:
        """Get the current registration count for an event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM (
                    SELECT user_id FROM registrations WHERE event_id = ?
                    UNION
                    SELECT user_id FROM rsvp_responses WHERE event_id = ?
                )
            """,
                (event_id, event_id),
            )
            result = cursor.fetchone()
            return result[0] if result else 0

    def is_event_at_capacity(self, event_id: int) -> bool:
        """Check if an event has reached its attendee limit"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT attendee_limit FROM events WHERE id = ?",
                (event_id,),
            )
            result = cursor.fetchone()

            if not result or result[0] is None:
                return False  # No limit set

            limit = result[0]
            current_count = self.get_registration_count(event_id)
            return current_count >= limit

    def set_rsvp_response(
        self, event_id: int, user_id: int, username: str, first_name: str, response: str
    ) -> str:
        """Set RSVP response for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if user has already responded
            cursor.execute(
                "SELECT response FROM rsvp_responses WHERE event_id = ? AND user_id = ?",
                (event_id, user_id),
            )
            existing_response = cursor.fetchone()
            previous_response = existing_response[0] if existing_response else None

            if existing_response:
                # Update existing response
                cursor.execute(
                    "UPDATE rsvp_responses SET response = ?, responded_at = ? WHERE event_id = ? AND user_id = ?",
                    (response, datetime.now().isoformat(), event_id, user_id),
                )
                action_message = f"✅ Изменен ответ: {previous_response} → {response}"
            else:
                # Insert new response
                cursor.execute(
                    "INSERT INTO rsvp_responses (event_id, user_id, username, first_name, response, responded_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        user_id,
                        username,
                        first_name,
                        response,
                        datetime.now().isoformat(),
                    ),
                )
                action_message = f"✅ Ваш ответ: {response}"

            conn.commit()
            return action_message

    def get_rsvp_stats(self, event_id: int) -> Dict[str, int]:
        """Get RSVP statistics for an event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response, COUNT(*) FROM rsvp_responses WHERE event_id = ? GROUP BY response",
                (event_id,),
            )
            results = cursor.fetchall()

            stats = {"иду": 0, "не иду": 0}
            for response, count in results:
                stats[response] = count

            return stats

    def get_user_rsvp_response(self, event_id: int, user_id: int) -> Optional[str]:
        """Get user's RSVP response for an event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response FROM rsvp_responses WHERE event_id = ? AND user_id = ?",
                (event_id, user_id),
            )
            result = cursor.fetchone()
            return result[0] if result else None

    def get_recent_rsvp_responses(self, event_id: int, limit: int = 5) -> List[Tuple]:
        """Get recent RSVP responses for an event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT first_name, username, response 
                FROM rsvp_responses 
                WHERE event_id = ? 
                ORDER BY responded_at DESC 
                LIMIT ?
            """,
                (event_id, limit),
            )
            return cursor.fetchall()

    def get_attending_usernames(self, event_id: int) -> List[str]:
        """Get list of usernames who will attend the event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT username
                FROM rsvp_responses
                WHERE event_id = ? AND response = 'иду'
                ORDER BY responded_at ASC
            """,
                (event_id,),
            )
            results = cursor.fetchall()
            return [
                f"@{username[0]}" if username[0] else "Unknown User"
                for username in results
            ]

    def get_attending_users(self, event_id: int) -> List[Tuple[str, str, int]]:
        """Get list of users (first_name, username, user_id) who will attend the event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT first_name, username, user_id
                FROM rsvp_responses
                WHERE event_id = ? AND response = 'иду'
                ORDER BY responded_at ASC
            """,
                (event_id,),
            )
            results = cursor.fetchall()
            return [
                (first_name or "Unknown", username or "", user_id)
                for first_name, username, user_id in results
            ]

    def get_events_with_registration_counts(self) -> List[Tuple]:
        """Get events with registration counts for admin view"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT e.id, e.title, e.event_date,
                       (COUNT(DISTINCT r.user_id) + COUNT(DISTINCT rs.user_id)) as total_users,
                       e.attendee_limit
                FROM events e
                LEFT JOIN registrations r ON e.id = r.event_id
                LEFT JOIN rsvp_responses rs ON e.id = rs.event_id
                WHERE e.is_active = 1
                GROUP BY e.id, e.title, e.event_date, e.attendee_limit
                ORDER BY e.event_date
            """
            )
            return cursor.fetchall()

    def get_active_events_for_notification(self) -> List[Tuple]:
        """Get active events with user counts for notification menu"""
        with self.get_connection() as conn:
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
            return cursor.fetchall()


# Global database instance
db = DatabaseManager()
