"""
Telegram bot (polling): forwards user text to agent.run_agent and sends the reply back.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent import run_agent
from config import TELEGRAM_BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE = 4096


def _chunks(text: str, limit: int = TELEGRAM_MAX_MESSAGE) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Send any text message. I’ll reply using Claude (with tools like weather)."
        )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    if not text:
        return

    chat = update.effective_chat
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    except Exception:
        pass

    # Extract the Telegram user ID so agent.py can load/save conversation history
    telegram_user_id = update.effective_user.id if update.effective_user else None

    try:
        reply = await asyncio.to_thread(run_agent, text, telegram_user_id)
    except Exception:
        logger.exception("run_agent failed")
        await update.message.reply_text("Sorry, something went wrong processing your message.")
        return

    for part in _chunks(reply):
        await update.message.reply_text(part)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("Set TELEGRAM_BOT_TOKEN in your project `.env` file.", file=sys.stderr)
        sys.exit(1)

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Starting Telegram polling (Ctrl+C to stop)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
