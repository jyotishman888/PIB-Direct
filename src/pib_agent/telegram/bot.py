import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from pib_agent.config import get_settings
from pib_agent.telegram import handlers

logger = logging.getLogger(__name__)


class TelegramConfigError(RuntimeError):
    """Raised when the bot is started without a configured TELEGRAM_BOT_TOKEN."""


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise TelegramConfigError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to .env before running the bot."
        )

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler(["start", "help"], handlers.start))
    application.add_handler(CommandHandler("ministries", handlers.ministries_command))
    application.add_handler(CommandHandler("subscribe", handlers.subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", handlers.unsubscribe_command))
    application.add_handler(CommandHandler("mysubs", handlers.mysubs_command))
    application.add_handler(
        CallbackQueryHandler(handlers.toggle_callback, pattern=r"^toggle:\d+$")
    )
    return application


def run_bot() -> None:
    application = build_application()
    logger.info("Starting Telegram bot (long polling)...")
    application.run_polling(drop_pending_updates=True)
