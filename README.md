# Telegram Event Bot

A Telegram bot for event management in closed channels with user registration, notifications, admin functionality, and RSVP system using python-telegram-bot framework.

## Features

### For Admins

- **Event Management**: Create, list, and manage events
- **Event Cards with RSVP**: Post event cards in chat groups with RSVP buttons
- **Registration Tracking**: View user registrations for events
- **Notifications**: Send notifications to registered users
- **RSVP Statistics**: View RSVP responses for events

### For Users

- **Event Discovery**: Browse available events
- **Registration**: Register for events with one click
- **RSVP Responses**: Respond to event cards with "иду" (I'm going) or "не иду" (I'm not going)
- **Notifications**: Receive event reminders and updates

## Commands

### Admin Commands

- `/admin` - Access admin panel
- `/create_event <title> <date> <description>` - Create event via command line
- `/list_events` - List all events with registration counts
- `/event_users <event_id>` - View users registered for specific event
- `/notify_users <event_id> <message>` - Send notification to event participants
- `/post_event_card <event_id>` - Post event card with RSVP buttons
- `/rsvp_stats <event_id>` - View RSVP statistics for an event

### User Commands

- `/start` - Welcome message
- `/events` - Show available events

## RSVP System

The bot includes a comprehensive RSVP system for event cards:

### How it Works

1. **Admin posts event card**: Use `/admin` → "🎫 Post Event Card" or `/post_event_card <event_id>`
2. **Event card appears**: Shows event details with two RSVP buttons: "✅ иду" and "❌ не иду"
3. **Users respond**: Click either button to record their RSVP
4. **Track responses**: Admins can view statistics using `/admin` → "📊 View RSVP Stats"

### RSVP Features

- **One response per user**: Users can only respond once per event
- **Real-time tracking**: Responses are stored in the database
- **Statistics**: View counts for "иду" and "не иду" responses
- **User-friendly**: Simple button interface in Russian

## Setup

### Environment Variables

Create a `.env` file with:

```
BOT_TOKEN=your_bot_token
ADMIN_IDS=123456789,987654321
CHANNEL_ID=@your_channel
```

### Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables

3. Run the bot:

```bash
python main.py
```

## Database Schema

The bot uses SQLite with three main tables:

### Events Table

- `id`: Primary key
- `title`: Event title
- `description`: Event description
- `event_date`: Event date (YYYY-MM-DD)
- `created_at`: Creation timestamp
- `is_active`: Active status

### Registrations Table

- `id`: Primary key
- `event_id`: Foreign key to events
- `user_id`: Telegram user ID
- `username`: Telegram username
- `first_name`: User's first name
- `registered_at`: Registration timestamp

### RSVP Responses Table

- `id`: Primary key
- `event_id`: Foreign key to events
- `user_id`: Telegram user ID
- `username`: Telegram username
- `first_name`: User's first name
- `response`: RSVP response ('иду' or 'не иду')
- `responded_at`: Response timestamp

## Usage Examples

### Creating and Posting an Event Card

1. Use `/admin` to access admin panel
2. Click "📅 Create Event" to create a new event
3. Fill in title, date, and description
4. Click "✅ Create Event" to save
5. Use "🎫 Post Event Card" to post RSVP card in chat
6. Select the event to post the card

### Viewing RSVP Statistics

1. Use `/admin` to access admin panel
2. Click "📊 View RSVP Stats"
3. Select an event to view statistics
4. See counts for "иду" and "не иду" responses

## Security Features

- Admin-only access to sensitive commands
- Input validation for all user inputs
- SQL injection prevention with parameterized queries
- Environment variable protection for sensitive data

## Error Handling

- Graceful error messages for users
- Comprehensive logging for debugging
- Input validation and sanitization
- Database connection error handling
