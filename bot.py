
import logging

# Настройка логирования
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    level=logging.INFO
)

# Отключаем лишние логи от библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

import asyncio
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import datetime


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
import os
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_USERNAME = '@priznavashki_Melovoe'
MODERATOR_IDS = [813475634, 5919268354]

# Хранилища
pending_messages = {}
moderation_logs = []
stats = defaultdict(lambda: {"approved": 0, "rejected": 0, "total": 0})
editing_contexts = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Напиши сообщение и выбери способ публикации.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.message.from_user
    user_id = user.id
    text = update.message.caption or update.message.text or ""
    user_name = user.first_name or user.username

    media = None
    media_type = None

    if update.message.photo:
        media = update.message.photo[-1].file_id
        media_type = "photo"
    elif update.message.video:
        media = update.message.video.file_id
        media_type = "video"
    elif update.message.voice:
        media = update.message.voice.file_id
        media_type = "voice"
    elif update.message.document:
        media = update.message.document.file_id
        media_type = "document"

    print(f"[LOG] Сообщение от @{user.username or 'no_username'} ({user.first_name or 'no_name'}). Тип: {media_type}, Текст: {text[:30]}...")

    pending_messages[user_id] = {
        "text": text,
        "user_name": user_name,
        "media": media,
        "media_type": media_type,
        "is_anon": True
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔘 Анонимно", callback_data="send_anon")],
        [InlineKeyboardButton("🙋 От имени", callback_data="send_named")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
    ])
    await update.message.reply_text("Как опубликовать?", reply_markup=keyboard)


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    choice = query.data

    if user_id not in pending_messages:
        await query.edit_message_text("Сообщение уже обработано.")
        return

    data = pending_messages[user_id]
    text = data["text"]
    user_name = data["user_name"]
    media = data["media"]
    media_type = data["media_type"]

    if choice == "cancel":
        del pending_messages[user_id]
        await query.edit_message_text("❌ Отправка отменена.")
        return

    is_anon = choice == "send_anon"
    data["is_anon"] = is_anon

    final_text = text if is_anon else f"📨 Сообщение от {user_name}:\n\n{text}"
    if media_type:
        final_text = final_text[:1024]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data=f"approve|{user_id}"),
            InlineKeyboardButton("🚫 Отклонить", callback_data=f"reject|{user_id}"),
            InlineKeyboardButton("✏ Редактировать", callback_data=f"edit|{user_id}")
        ]
    ])

    async def send_to_moderators():
        for mod_id in MODERATOR_IDS:
            try:
                if media_type == "photo":
                    await context.bot.send_photo(chat_id=mod_id, photo=media, caption=final_text, reply_markup=keyboard)
                elif media_type == "video":
                    await context.bot.send_video(chat_id=mod_id, video=media, caption=final_text, reply_markup=keyboard)
                elif media_type == "voice":
                    await context.bot.send_voice(chat_id=mod_id, voice=media, caption=final_text, reply_markup=keyboard)
                elif media_type == "document":
                    await context.bot.send_document(chat_id=mod_id, document=media, caption=final_text, reply_markup=keyboard)
                else:
                    await context.bot.send_message(chat_id=mod_id, text=final_text, reply_markup=keyboard)
            except Exception as e:
                print(f"[ERROR] Ошибка при отправке модератору {mod_id}: {e}")

    asyncio.create_task(send_to_moderators())
    await query.edit_message_text("✉️ Сообщение отправлено на модерацию.")


async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split('|')
    action, target_id = parts[0], int(parts[1])
    mod_id = query.from_user.id
    mod_name = query.from_user.username or query.from_user.first_name

    if target_id not in pending_messages:
        await query.edit_message_text("Сообщение уже обработано.")
        return

    data = pending_messages.pop(target_id)
    text = data["text"]
    is_anon = data["is_anon"]
    media = data["media"]
    media_type = data["media_type"]
    user_name = data["user_name"]

    final_text = text if is_anon else f"📨 Сообщение от {user_name}:\n\n{text}"
    if media_type:
        final_text = final_text[:1024]

    today = str(datetime.date.today())
    stats[today]["total"] += 1

    if action == "approve":
        try:
            if media_type == "photo":
                await context.bot.send_photo(CHANNEL_USERNAME, photo=media, caption=final_text)
            elif media_type == "video":
                await context.bot.send_video(CHANNEL_USERNAME, video=media, caption=final_text)
            elif media_type == "voice":
                await context.bot.send_voice(CHANNEL_USERNAME, voice=media, caption=final_text)
            elif media_type == "document":
                await context.bot.send_document(CHANNEL_USERNAME, document=media, caption=final_text)
            else:
                await context.bot.send_message(CHANNEL_USERNAME, text=final_text)

            await context.bot.send_message(chat_id=target_id, text="✅ Ваше сообщение опубликовано!")
            await query.edit_message_text("✅ Опубликовано.")
            stats[today]["approved"] += 1
            moderation_logs.append((f"@{mod_name}", "approve", f"@{user_name}" if not is_anon else "анонимно"))
        except Exception as e:
            print(f"[ERROR] При публикации: {e}")
    elif action == "reject":
        await context.bot.send_message(chat_id=target_id, text="❌ Ваше сообщение отклонено модератором.")
        await query.edit_message_text("🚫 Отклонено.")
        stats[today]["rejected"] += 1
        moderation_logs.append((f"@{mod_name}", "reject", f"@{user_name}" if not is_anon else "анонимно"))
    elif action == "edit":
        editing_contexts[mod_id] = {"user_id": target_id, "data": data}
        await context.bot.send_message(mod_id, text="✏ Пришлите отредактированный текст.")
        await query.edit_message_text("📝 Ожидаю новый текст.")


async def receive_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mod_id = update.effective_user.id
    if mod_id not in editing_contexts:
        return

    new_text = update.message.text
    ctx = editing_contexts.pop(mod_id)
    user_id = ctx["user_id"]
    data = ctx["data"]
    data["text"] = new_text
    pending_messages[user_id] = data
    await update.message.reply_text("✅ Текст обновлён. Вернитесь к кнопке публикации.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in MODERATOR_IDS:
        return

    msg = "📊 Статистика:\n"
    for day, values in sorted(stats.items(), reverse=True):
        msg += f"{day} — ✅ {values['approved']} / 🚫 {values['rejected']} / 📨 {values['total']}\n"
    
    msg += "\n📝 Последние действия модераторов:\n"
    for log in moderation_logs[-10:][::-1]:  # Последние 10 записей в обратном порядке
        msg += f"{log[0]} {log[1]} сообщение от {log[2]}\n"
    
    await update.message.reply_text(msg)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Не понимаю команду. Просто напиши сообщение 🙂")



async def error_handler(update, context):
    logger.error("Произошла ошибка:", exc_info=context.error)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(MODERATOR_IDS), receive_edit))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_choice, pattern="^(send_anon|send_named|cancel)$"))
    app.add_handler(CallbackQueryHandler(moderate, pattern="^(approve|reject|edit)\|"))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    print("Бот запущен.")
    
import os
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", f"https://your-railway-url.up.railway.app/{BOT_TOKEN}")

async def set_webhook():
    await app.bot.set_webhook(url=WEBHOOK_URL)

app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_path=f"/{BOT_TOKEN}",
    on_startup=[set_webhook]
)



if __name__ == '__main__':
    main()