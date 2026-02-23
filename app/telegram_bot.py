import asyncio
import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage, AIMessage

from app.config import settings
from app.database import SessionLocal
from app.models.models import Conversation, Message
from app.agent.agent import Agent

logger = logging.getLogger(__name__)

telegram_app: Optional[Application] = None


class TypingIndicator:
    def __init__(self, bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def _send_typing_loop(self):
        while self._running:
            try:
                await self.bot.send_chat_action(
                    chat_id=self.chat_id,
                    action="typing"
                )
                await asyncio.sleep(4)
            except Exception as e:
                logger.error(f"Error sending typing action: {e}")
                break
    
    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._send_typing_loop())
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Hello! I'm your AI Agent assistant.\n\n"
        "I can remember information about you and help with various tasks.\n\n"
        "Just send me a message to start chatting!\n\n"
        "Commands:\n"
        "/new - Start a new conversation\n"
        "/clear - Clear current conversation"
    )


async def new_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        telegram_user_id = update.effective_user.id
        
        conversation = Conversation(
            title=f"Telegram Chat",
            extra_data={"telegram_user_id": telegram_user_id}
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        
        context.user_data["conversation_id"] = str(conversation.id)
        
        await update.message.reply_text(
            "✅ Started a new conversation! How can I help you?"
        )
    finally:
        db.close()


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "conversation_id" in context.user_data:
        db = SessionLocal()
        try:
            conversation_id = context.user_data["conversation_id"]
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()
            if conversation:
                db.delete(conversation)
                db.commit()
            del context.user_data["conversation_id"]
        finally:
            db.close()
    
    await update.message.reply_text("🗑️ Conversation cleared. Use /new to start fresh!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    db = SessionLocal()
    try:
        telegram_user_id = update.effective_user.id
        user_message = update.message.text
        
        conversation_id = context.user_data.get("conversation_id")
        
        if not conversation_id:
            conversation = Conversation(
                title=f"Telegram Chat",
                extra_data={"telegram_user_id": telegram_user_id}
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = str(conversation.id)
            context.user_data["conversation_id"] = conversation_id
        else:
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()
            if not conversation:
                conversation = Conversation(
                    title=f"Telegram Chat",
                    extra_data={"telegram_user_id": telegram_user_id}
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
                conversation_id = str(conversation.id)
                context.user_data["conversation_id"] = conversation_id
        
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=user_message
        )
        db.add(user_msg)
        db.commit()
        
        previous_messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).all()
        
        langchain_messages = [
            HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content)
            for m in previous_messages
        ]
        
        typing = TypingIndicator(context.bot, update.effective_chat.id)
        typing.start()
        
        try:
            agent = Agent(db, conversation_id)
            result = agent.invoke(langchain_messages)
            
            ai_message_content = result["messages"][-1].content
            
            ai_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_message_content
            )
            db.add(ai_message)
            db.commit()
            
            await update.message.reply_text(ai_message_content)
        finally:
            await typing.stop()
        
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(
            "Sorry, there was an error processing your message. Please try again."
        )
    finally:
        db.close()


def setup_telegram_bot() -> Optional[Application]:
    global telegram_app
    
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot will not run.")
        return None
    
    telegram_app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("new", new_conversation_command))
    telegram_app.add_handler(CommandHandler("clear", clear_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return telegram_app


async def start_telegram_bot():
    app = setup_telegram_bot()
    if app:
        try:
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            logger.info("Telegram bot started successfully!")
        except Exception as e:
            logger.error(f"Telegram bot failed to start: {e}")


async def stop_telegram_bot():
    global telegram_app
    if telegram_app:
        if telegram_app.updater and telegram_app.updater.running:
            await telegram_app.updater.stop()
        if telegram_app.running:
            await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram bot stopped.")
