import os
from dotenv import load_dotenv

import logging
from datetime import time
from telegram import (
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)

from src.constants import TOPIC, LOCATION, LANGUAGE, AUTOMATIC

from src.db_tools import init_database

from src.handlers import (
    start,
    button_callback,
    settings,
    toggle_automatic,
    send_daily_updates,
    topic,
    location,
    language,
    automatic,
    cancel,
)

load_dotenv()
# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Start the bot."""
    # Initialize database
    init_database()

    # Replace with your bot token from @BotFather
    BOT_TOKEN = os.getenv("TOKEN")

    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(button_callback, pattern="^(use_saved|update_prefs)$"),
        ],
        states={
            TOPIC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, topic),
                CallbackQueryHandler(
                    button_callback, pattern="^(use_saved|update_prefs)$"
                ),
            ],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, location)],
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language)],
            AUTOMATIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, automatic)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("settings", settings))
    # application.add_handler(
    #     CallbackQueryHandler(button_callback, pattern="^(use_saved|update_prefs)$")
    # )
    application.add_handler(
        CallbackQueryHandler(toggle_automatic, pattern="^toggle_auto$")
    )

    # Schedule daily updates at 7:00 AM
    job_queue = application.job_queue
    job_queue.run_daily(
        send_daily_updates,
        time=time(hour=7, minute=0, second=0),
        name="daily_news_updates",
    )

    logger.info("Bot started with daily updates scheduled at 7:00 AM!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
