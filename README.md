# Telegram Event Bot

A Telegram bot for event management in closed channels with user registration, notifications, and admin functionality using python-telegram-bot framework.

## Features

- **Event Management**: Create, list, and manage events with RSVP functionality
- **User Registration**: Users can register for events with inline buttons
- **RSVP System**: Interactive RSVP cards with real-time statistics
- **Admin Panel**: Comprehensive admin interface for event management
- **Notifications**: Send notifications to registered users
- **User Status Checking**: Verify which users can receive notifications
- **Database Storage**: SQLite database for persistent data storage

## Project Structure

```
event_tg_bot/
├── bot.py                 # Main bot class and application setup
├── config.py              # Configuration management and environment variables
├── database.py            # Database operations and SQLite management
├── main.py                # Application entry point
├── main_original.py       # Original monolithic code (backup)
├── requirements.txt       # Python dependencies
├── events.db             # SQLite database file
├── .env                  # Environment variables (create this)
├── handlers/             # Command and callback handlers
│   ├── __init__.py
│   ├── admin_handlers.py    # Admin command handlers
│   ├── user_handlers.py     # Public user handlers
│   ├── callback_handlers.py # Inline keyboard callback handlers
│   └── message_handlers.py  # Text message input handlers
└── utils/                # Utility functions
    ├── __init__.py
    ├── keyboard_utils.py    # Inline keyboard creation utilities
    └── message_utils.py     # Message formatting utilities
```

## Installation

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd event_tg_bot
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Create environment file**:
   Create a `.env` file in the project root with the following variables:

   ```env
   BOT_TOKEN=your_bot_token_here
   ADMIN_IDS=123456789,987654321
   CHANNEL_ID=@your_channel
   ```

4. **Run the bot**:
   ```bash
   python main.py
   ```

## Configuration

### Environment Variables

- `BOT_TOKEN`: Your Telegram bot token from @BotFather
- `ADMIN_IDS`: Comma-separated list of admin user IDs
- `CHANNEL_ID`: Optional channel ID for posting events

### Database

The bot uses SQLite for data storage. The database file (`events.db`) will be created automatically on first run.

**Tables:**

- `events`: Event information (title, description, date, etc.)
- `registrations`: User registrations for events
- `rsvp_responses`: RSVP responses for event cards

## Usage

### Admin Commands

- `/admin` - Open admin panel
- `/create_event <title> <date> <description>` - Create event via command
- `/list_events` - List all events with registration counts
- `/event_users <event_id>` - Show users registered for specific event
- `/notify_users <event_id> <message>` - Send notification to event users
- `/post_event_card <event_id>` - Post RSVP card in chat
- `/rsvp_stats <event_id>` - Show RSVP statistics
- `/check_users <event_id>` - Check user notification status

### Public Commands

- `/start` - Welcome message and bot introduction
- `/events` - Show available events for registration

### Admin Panel Features

1. **Event Creation**: Interactive dialogue for creating events
2. **Event Management**: View and manage all events
3. **Registration Tracking**: Monitor user registrations
4. **Notification System**: Send custom notifications
5. **RSVP Management**: Post and track RSVP responses
6. **User Status**: Check which users can receive notifications

## Architecture

### Code Organization

The project follows a modular architecture with clear separation of concerns:

- **Configuration**: Centralized configuration management
- **Database**: Abstracted database operations with context managers
- **Handlers**: Separated by functionality (admin, user, callbacks, messages)
- **Utilities**: Reusable functions for keyboards and message formatting
- **Main Bot**: Orchestrates all components

### Key Design Patterns

- **Dependency Injection**: Handlers receive bot instance for access to shared resources
- **Context Managers**: Database connections are managed safely
- **Separation of Concerns**: Each module has a single responsibility
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Logging**: Structured logging throughout the application

### Database Operations

All database operations are centralized in the `DatabaseManager` class:

```python
from database import db

# Create event
event_id = db.create_event(title, description, date)

# Get events
events = db.get_active_events()

# Register user
success = db.register_user_for_event(event_id, user_id, username, first_name)
```

### Handler Structure

Handlers are organized by functionality:

- **AdminHandlers**: Admin-only commands and callbacks
- **UserHandlers**: Public user commands
- **CallbackHandlers**: Inline keyboard interactions
- **MessageHandlers**: Text input processing

## Development

### Adding New Features

1. **Database**: Add methods to `DatabaseManager` in `database.py`
2. **Handlers**: Add handler methods to appropriate handler class
3. **Utilities**: Add helper functions to `utils/` modules
4. **Configuration**: Add new config options to `config.py`

### Testing

The bot can be tested by:

1. Running in development mode
2. Using test events and users
3. Monitoring logs for debugging
4. Testing all admin and user flows

### Logging

The application uses structured logging:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Operation completed successfully")
logger.error("Error occurred: %s", error_message)
```

## Security Considerations

- Admin permissions are checked on every admin operation
- User input is validated and sanitized
- Database queries use parameterized statements
- Environment variables are used for sensitive data
- Error messages don't expose internal details

## Troubleshooting

### Common Issues

1. **Bot not responding**: Check bot token and internet connection
2. **Database errors**: Ensure write permissions in project directory
3. **Admin commands not working**: Verify admin IDs in environment variables
4. **Notifications failing**: Users must start conversation with bot first

### Debug Mode

Enable debug logging by modifying the logging level in `main.py`:

```python
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

1. Follow the existing code structure and patterns
2. Add appropriate error handling and logging
3. Update documentation for new features
4. Test thoroughly before submitting changes

## License

This project is licensed under the MIT License - see the LICENSE file for details.
