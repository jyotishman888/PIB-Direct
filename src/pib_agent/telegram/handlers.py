import asyncio
import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from pib_agent.telegram.keyboards import build_ministries_keyboard
from pib_agent.telegram.subscriptions import (
    list_subscriptions,
    subscribe_by_slug,
    toggle_subscription,
    unsubscribe_by_slug,
)

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "\U0001f44b Welcome to PIB Digest!\n\n"
    "I'll send you Claude-summarized PIB (Press Information Bureau) releases for "
    "the ministries you follow, with UPSC-relevant releases flagged.\n\n"
    "Commands:\n"
    "/ministries — pick which ministries to follow\n"
    "/mysubs — see your current subscriptions\n"
    "/subscribe <ministry-slug> — subscribe directly\n"
    "/unsubscribe <ministry-slug> — unsubscribe directly"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(WELCOME_TEXT)
    await _send_ministries_keyboard(update)


async def ministries_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_ministries_keyboard(update)


async def _send_ministries_keyboard(update: Update) -> None:
    if update.effective_chat is None or update.effective_message is None:
        return
    chat_id = update.effective_chat.id
    keyboard = await asyncio.to_thread(build_ministries_keyboard, chat_id)
    await update.effective_message.reply_text(
        "Tap a ministry to subscribe or unsubscribe:", reply_markup=keyboard
    )


async def toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None or update.effective_chat is None:
        return

    ministry_id = int(query.data.split(":", 1)[1])
    chat_id = update.effective_chat.id
    subscribed = await asyncio.to_thread(toggle_subscription, chat_id, ministry_id)

    await query.answer("Subscribed" if subscribed else "Unsubscribed")
    keyboard = await asyncio.to_thread(build_ministries_keyboard, chat_id)
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except BadRequest as exc:
        # e.g. "Message is not modified" if the tap raced a concurrent toggle.
        logger.debug("Could not refresh ministries keyboard after toggle: %s", exc)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "Usage: /subscribe <ministry-slug>\nSee /ministries for the list."
        )
        return

    slug = context.args[0].strip().lower()
    ministry = await asyncio.to_thread(subscribe_by_slug, chat_id, slug)
    if ministry is None:
        await update.message.reply_text(
            f"Unknown ministry slug: {slug}\nSee /ministries for valid options."
        )
        return
    await update.message.reply_text(f"Subscribed to {ministry.name}.")


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "Usage: /unsubscribe <ministry-slug>\nSee /mysubs for your subscriptions."
        )
        return

    slug = context.args[0].strip().lower()
    ministry = await asyncio.to_thread(unsubscribe_by_slug, chat_id, slug)
    if ministry is None:
        await update.message.reply_text(f"Unknown ministry slug: {slug}")
        return
    await update.message.reply_text(f"Unsubscribed from {ministry.name}.")


async def mysubs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        return
    chat_id = update.effective_chat.id

    ministries = await asyncio.to_thread(list_subscriptions, chat_id)
    if not ministries:
        await update.message.reply_text(
            "You're not subscribed to any ministries yet. Use /ministries to pick some."
        )
        return

    lines = "\n".join(f"• {m.name}" for m in ministries)
    await update.message.reply_text(f"Your subscriptions:\n{lines}")
