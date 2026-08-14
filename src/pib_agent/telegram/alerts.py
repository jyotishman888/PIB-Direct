"""Operational alerts to the admin's Telegram chat.

Separate from `notify` on purpose: that module is about delivering content to
subscribers, this one is about telling the operator the machine is unwell.
They share a bot token and nothing else.
"""

import asyncio
import html
import logging

import telegram

from pib_agent.config import get_settings

logger = logging.getLogger(__name__)

_MAX_ALERT_CHARS = 3500  # Telegram's hard limit is 4096; leave room for markup.


async def _send_async(token: str, chat_id: int, text: str) -> None:
    async with telegram.Bot(token=token) as bot:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=telegram.constants.ParseMode.HTML,
            disable_web_page_preview=True,
        )


def send_ops_alert(subject: str, body: str = "") -> bool:
    """Send an operational alert. Returns True if a message actually went out.

    Never raises. An alert is a diagnostic, not part of the work — a failure
    to report a problem must not become a second problem, and in particular
    must not fail the pipeline run that triggered it.
    """
    settings = get_settings()

    if not settings.ops_alerts_enabled:
        return False
    if not settings.telegram_bot_token or settings.telegram_admin_chat_id is None:
        logger.debug("Ops alert suppressed: no bot token or admin chat configured.")
        return False

    text = f"⚠️ <b>{html.escape(subject)}</b>"
    if body:
        text += f"\n\n<pre>{html.escape(body[:_MAX_ALERT_CHARS])}</pre>"

    try:
        asyncio.run(_send_async(settings.telegram_bot_token, settings.telegram_admin_chat_id, text))
    except Exception:
        logger.exception("Failed to send ops alert (original problem is logged separately).")
        return False

    return True
