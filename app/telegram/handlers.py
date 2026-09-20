"""Telegram message handlers, update deduplication, inline keyboards, voice notes, and artifact dispatching."""

import os
import re
import tempfile
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from app.database.db import get_db
from app.database.repositories import TelegramUpdateRepository
from app.services.billing_service import BillingService
from app.agent.orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)

orchestrator = AgentOrchestrator()


def format_telegram_message(text: str) -> str:
    """Format Markdown into clean Telegram HTML (convert **bold** to <b>bold</b>, etc.)."""
    if not text:
        return ""
    # Convert ### headers to bold
    formatted = re.sub(r"^###\s*(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    formatted = re.sub(r"^##\s*(.+)$", r"<b>\1</b>", formatted, flags=re.MULTILINE)
    # Convert **bold** to <b>bold</b>
    formatted = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", formatted)
    # Convert __bold__ to <b>bold</b>
    formatted = re.sub(r"__(.+?)__", r"<b>\1</b>", formatted)
    # Convert *italic* to <i>italic</i> (when not starting line as bullet)
    formatted = re.sub(r"(?<!^)\*([^\*\n]+?)\*", r"<i>\1</i>", formatted, flags=re.MULTILINE)
    return formatted


def get_bill_action_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons for quick billing actions."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Finalize Bill", callback_data="action_finalize"),
            InlineKeyboardButton("📄 Get PDF", callback_data="action_pdf"),
            InlineKeyboardButton("❌ Cancel", callback_data="action_cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_text = (
        "🛒 <b>Welcome to Supermarket Ops Agent!</b>\n\n"
        "I am your AI assistant for running store operations right here on Telegram.\n\n"
        "<b>What you can say:</b>\n"
        "• <i>'What are the available items?'</i>\n"
        "• <i>'Want 2 packets of maggi'</i>\n"
        "• <i>'Also add 1 amul butter'</i>\n"
        "• <i>'50 packets of Maggi came in, cost ₹12, MRP ₹14'</i>\n"
        "• <i>'Drop the butter, make it 6 Maggi'</i>\n"
        "• <i>'Finalize bill'</i>\n"
        "• <i>'How much sugar is left?'</i>\n"
        "• <i>'What\\'s running out?'</i>\n"
        "• <i>'Put ₹500 on Ramesh\\'s credit'</i>\n"
        "• <i>'Ramesh paid ₹300'</i>\n"
        "• <i>'Today\\'s sales?'</i>\n"
        "• <i>'Send me that bill as a PDF'</i>\n"
        "• <i>'Make this week\\'s sales analysis deck'</i>\n"
        "• <i>'Close the day'</i>\n"
        "• <i>'Always assume UPI unless I say cash'</i>\n\n"
        "<i>You can also send voice notes!</i>\n"
        "Type /new to start a fresh conversation at any time."
    )
    if update.effective_message:
        await update.effective_message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


async def new_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /new or /reset command."""
    chat_id = update.effective_chat.id if update.effective_chat else 0
    orchestrator.reset_chat(chat_id)
    if update.effective_message:
        await update.effective_message.reply_text(
            "🔄 <b>Conversation session reset!</b> Your catalog, customer records, and store preferences remain safely preserved.",
            parse_mode=ParseMode.HTML,
        )


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interactive button taps on inline keyboards."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    chat_id = update.effective_chat.id
    action = query.data

    if action == "action_finalize":
        user_text = "finalize"
    elif action == "action_pdf":
        user_text = "send me that bill as a PDF"
    elif action == "action_cancel":
        user_text = "cancel bill"
    else:
        return

    try:
        with get_db() as session:
            agent_response = orchestrator.process_message(
                chat_id=chat_id,
                user_text=user_text,
                session=session,
            )

        formatted_text = format_telegram_message(agent_response.text)
        await query.message.reply_text(formatted_text, parse_mode=ParseMode.HTML)

        for artifact in agent_response.artifacts:
            file_path = artifact.get("file_path")
            if file_path and os.path.exists(file_path):
                caption = "📄 Tax Invoice PDF" if artifact.get("type") == "pdf_invoice" else "📊 Sales Analysis Presentation"
                with open(file_path, "rb") as doc_file:
                    await query.message.reply_document(
                        document=doc_file,
                        caption=caption,
                    )
    except Exception as e:
        logger.exception(f"Error handling callback {action}: {e}")
        await query.message.reply_text(f"Action failed: {e}")


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribe voice messages using SpeechRecognition and pass to agent."""
    if not update.effective_message or not update.effective_message.voice:
        return

    chat_id = update.effective_chat.id
    await update.effective_message.reply_text("🎙️ <i>Processing your voice note...</i>", parse_mode=ParseMode.HTML)

    try:
        voice = await context.bot.get_file(update.effective_message.voice.file_id)
        with tempfile.TemporaryDirectory() as tmp_dir:
            ogg_path = os.path.join(tmp_dir, "voice.ogg")
            wav_path = os.path.join(tmp_dir, "voice.wav")
            await voice.download_to_drive(ogg_path)

            from pydub import AudioSegment
            import speech_recognition as sr

            sound = AudioSegment.from_file(ogg_path)
            sound.export(wav_path, format="wav")

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
                try:
                    transcribed_text = recognizer.recognize_google(audio_data, language="en-IN")
                except sr.UnknownValueError:
                    await update.effective_message.reply_text("Could not clearly understand the audio. Please speak clearly or type.")
                    return
                except Exception as ex:
                    logger.warning(f"Voice recognition error: {ex}")
                    await update.effective_message.reply_text(f"Voice recognition service error: {ex}")
                    return

            await update.effective_message.reply_text(f"🗣️ <i>You said:</i> \"{transcribed_text}\"", parse_mode=ParseMode.HTML)

            with get_db() as session:
                agent_response = orchestrator.process_message(
                    chat_id=chat_id,
                    user_text=transcribed_text,
                    session=session,
                )

            # Check if active draft bill exists to show keyboard
            with get_db() as s:
                b_svc = BillingService(s)
                active_draft = b_svc.get_current_bill(chat_id)
            reply_markup = get_bill_action_keyboard() if (active_draft and active_draft.get("items")) else None

            formatted_text = format_telegram_message(agent_response.text)
            try:
                await update.effective_message.reply_text(formatted_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            except Exception:
                await update.effective_message.reply_text(agent_response.text, reply_markup=reply_markup)

            for artifact in agent_response.artifacts:
                file_path = artifact.get("file_path")
                if file_path and os.path.exists(file_path):
                    caption = "📄 Tax Invoice PDF" if artifact.get("type") == "pdf_invoice" else "📊 Weekly Sales Analysis Presentation"
                    with open(file_path, "rb") as doc_file:
                        await update.effective_message.reply_document(document=doc_file, caption=caption)

    except Exception as e:
        logger.exception(f"Error handling voice note: {e}")
        await update.effective_message.reply_text("Sorry, I had trouble processing that voice note. Please type your request.")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle photos (handwritten grocery slips, paper bills, barcode/shelf pictures)
    using Gemini Multimodal Vision.
    """
    if not update.effective_message or not update.effective_message.photo:
        return

    update_id = update.update_id
    chat_id = update.effective_chat.id
    caption = update.effective_message.caption or ""

    # 1. Database idempotency check for Telegram update
    with get_db() as session:
        update_repo = TelegramUpdateRepository(session)
        if update_repo.is_already_processed(update_id):
            logger.warning(f"Telegram photo update {update_id} already processed. Skipping.")
            return
        update_repo.mark_processed(update_id)

    status_msg = await update.effective_message.reply_text(
        "🔍 <b>Analyzing photo with Gemini Vision...</b>\n<i>Reading items, quantities, and prices...</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        largest_photo = update.effective_message.photo[-1]
        photo_file = await context.bot.get_file(largest_photo.file_id)
        image_bytes = await photo_file.download_as_bytearray()

        with get_db() as session:
            agent_response = orchestrator.process_image(
                chat_id=chat_id,
                image_bytes=bytes(image_bytes),
                mime_type="image/jpeg",
                caption=caption,
                session=session,
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        reply_markup = None
        try:
            with get_db() as s:
                b_svc = BillingService(s)
                active_draft = b_svc.get_current_bill(chat_id)
                if active_draft and active_draft.get("items"):
                    reply_markup = get_bill_action_keyboard()
                elif any(w in agent_response.text.lower() for w in ["draft bill", "bill #", "items:"]):
                    reply_markup = get_bill_action_keyboard()
        except Exception:
            pass

        formatted_text = format_telegram_message(agent_response.text)
        try:
            await update.effective_message.reply_text(
                formatted_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except Exception:
            await update.effective_message.reply_text(
                agent_response.text,
                reply_markup=reply_markup,
            )

        for artifact in agent_response.artifacts:
            file_path = artifact.get("file_path")
            if file_path and os.path.exists(file_path):
                caption_doc = "📄 Tax Invoice PDF" if artifact.get("type") == "pdf_invoice" else "📊 Presentation Deck"
                with open(file_path, "rb") as doc_file:
                    await update.effective_message.reply_document(
                        document=doc_file,
                        caption=caption_doc,
                    )

    except Exception as e:
        logger.exception(f"Error processing photo: {e}")
        try:
            await status_msg.edit_text(f"❌ Failed to process photo: {e}")
        except Exception:
            await update.effective_message.reply_text(f"❌ Error analyzing photo: {e}")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main conversational message dispatcher with strict idempotency check.
    Prevents duplicate side-effects if Telegram redelivers an update.
    """
    if not update.effective_message or not update.effective_message.text:
        return

    update_id = update.update_id
    chat_id = update.effective_chat.id
    user_text = update.effective_message.text.strip()

    # 1. Database idempotency check for Telegram update
    with get_db() as session:
        update_repo = TelegramUpdateRepository(session)
        if update_repo.is_already_processed(update_id):
            logger.warning(f"Telegram update {update_id} already processed. Skipping to avoid duplicate side effects.")
            return
        update_repo.mark_processed(update_id)

    # 2. Process message through the Agent Orchestrator
    try:
        with get_db() as session:
            agent_response = orchestrator.process_message(
                chat_id=chat_id,
                user_text=user_text,
                session=session,
            )

        # 3. Check if reply should include interactive buttons
        # Always attach buttons if an active draft bill exists in database
        reply_markup = None
        try:
            with get_db() as s:
                b_svc = BillingService(s)
                active_draft = b_svc.get_current_bill(chat_id)
                if active_draft and active_draft.get("items"):
                    reply_markup = get_bill_action_keyboard()
                elif any(w in agent_response.text.lower() for w in ["draft bill", "bill #", "items:"]):
                    reply_markup = get_bill_action_keyboard()
        except Exception:
            if "bill" in agent_response.text.lower():
                reply_markup = get_bill_action_keyboard()

        # 4. Format Markdown into clean Telegram HTML (convert **text** to <b>text</b>)
        formatted_text = format_telegram_message(agent_response.text)

        # 5. Send text reply
        try:
            await update.effective_message.reply_text(
                formatted_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except Exception as pe:
            logger.warning(f"HTML parse error ({pe}), falling back to plain text")
            await update.effective_message.reply_text(
                agent_response.text,
                reply_markup=reply_markup,
            )

        # 6. If artifacts (PDF invoice, PPTX deck) were generated, send them as documents
        for artifact in agent_response.artifacts:
            file_path = artifact.get("file_path")
            if file_path and os.path.exists(file_path):
                caption = "📄 Tax Invoice PDF" if artifact.get("type") == "pdf_invoice" else "📊 Weekly Sales Analysis Presentation"
                with open(file_path, "rb") as doc_file:
                    await update.effective_message.reply_document(
                        document=doc_file,
                        caption=caption,
                    )

    except Exception as e:
        logger.exception(f"Unhandled error in message_handler for chat {chat_id}: {e}")
        await update.effective_message.reply_text(
            "I encountered an unexpected error while processing your request. Please check your inputs or try again."
        )
