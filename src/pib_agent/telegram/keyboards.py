from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from pib_agent.telegram.subscriptions import get_subscribed_ministry_ids, list_ministries


def build_ministries_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    ministries = list_ministries()
    subscribed_ids = get_subscribed_ministry_ids(chat_id)

    rows = [
        [
            InlineKeyboardButton(
                f"{'✅ ' if ministry.id in subscribed_ids else ''}{ministry.name}",
                callback_data=f"toggle:{ministry.id}",
            )
        ]
        for ministry in ministries
    ]
    return InlineKeyboardMarkup(rows)
