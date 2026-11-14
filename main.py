import os, io, asyncio, re
from datetime import datetime, timedelta
from PIL import Image
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from post import post_carousel_to_instagram
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
PROMPT = "Write a SHORT Roopkatha style Instagram caption in ENGLISH for these photos. Max 2 lines caption, very sweet and catchy. Then 1 line CTA - DM to order. Then only 6 hashtags. Do NOT write long story, keep it short. Only English."

albums = {}
album_tasks = {}

async def make_caption(imgs):
    response = client.models.generate_content(model="gemini-3.5-flash-lite", contents=[PROMPT] + imgs)
    return response.text

async def process_album_after_delay(chat_id, context):
    await asyncio.sleep(4)
    album = albums.get(chat_id, [])
    if not album: return
    albums[chat_id] = []
    if chat_id in album_tasks: del album_tasks[chat_id]
    await context.bot.send_message(chat_id, f"{len(album)} ta photo peye gechi! ✅ Caption banacchi...")
    try:
        imgs = []
        for b in album:
            img = Image.open(io.BytesIO(b)); img.thumbnail((768,768)); imgs.append(img)
        caption = await make_caption(imgs)
        context.application.bot_data[f"caption_{chat_id}"] = caption
        context.application.bot_data[f"last_album_{chat_id}"] = album
        context.application.bot_data[f"state_{chat_id}"] = "caption_ready"
        context.application.bot_data[f"song_{chat_id}"] = ""
        await context.bot.send_message(chat_id, f"Caption ready! 👇\n\n{caption}\n\nPochondo? 'HA' likh.\nPochondo na hole 'ABAR' likh.")
    except Exception as e:
        await context.bot.send_message(chat_id, f"Caption banate problem holo: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    if chat_id not in albums: albums[chat_id] = []
    albums[chat_id].append(bytes(photo_bytes))
    if chat_id in album_tasks: album_tasks[chat_id].cancel()
    album_tasks[chat_id] = asyncio.create_task(process_album_after_delay(chat_id, context))

def parse_time(text):
    text = text.lower().strip()
    if text in ["ekhon","ekhoni","now"]: return 0
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m: return None
    hour = int(m.group(1)); minute = int(m.group(2) or 0); ap = m.group(3)
    if ap == "pm" and hour != 12: hour += 12
    if ap == "am" and hour == 12: hour = 0
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "kal" in text or "tomorrow" in text: target += timedelta(days=1)
    if target <= now: target += timedelta(days=1)
    return (target - now).total_seconds()

async def scheduled_post(chat_id, context, delay_sec, time_text):
    await asyncio.sleep(delay_sec)
    caption = context.application.bot_data.get(f"caption_{chat_id}", "Roopkatha")
    song = context.application.bot_data.get(f"song_{chat_id}", "")
    album = context.application.bot_data.get(f"last_album_{chat_id}", [])
    if song:
        await context.bot.send_message(chat_id, f"⏰ DRAFT READY! {time_text} hoye geche.\n\n📝 Ebar Insta khule post kor:")
        for b in album:
            await context.bot.send_photo(chat_id, photo=io.BytesIO(b))
        await context.bot.send_message(chat_id, f"🎵 Gaan: {song}\n\n📝 Caption:\n{caption}\n\n👉 Insta app e giye ei photo gulo select kor -> Gaan add kor: {song} -> Caption paste kor -> Post!")
        context.application.bot_data[f"state_{chat_id}"] = "done"
        return
    result = post_carousel_to_instagram(album, caption)
    await context.bot.send_message(chat_id, f"⏰ {time_text} e auto post hoye gelo! ✅\n{result}")
    context.application.bot_data[f"state_{chat_id}"] = "done"

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.lower().strip()
    state = context.application.bot_data.get(f"state_{chat_id}", "")
    if state == "waiting_song":
        if text in ["no song","no","gaan lagbe na","lagbe na"]:
            context.application.bot_data[f"song_{chat_id}"] = ""
            context.application.bot_data[f"state_{chat_id}"] = "waiting_time"
            await update.message.reply_text("Thik ache, gaan charai auto post korbo.\n\nKotay post korbo?\n'EKHON' / '6 PM' / 'KAL 10 AM' likh.")
            return
        context.application.bot_data[f"song_{chat_id}"] = update.message.text
        context.application.bot_data[f"state_{chat_id}"] = "waiting_time"
        await update.message.reply_text(f"🎵 Gaan save kore nilam: {update.message.text}\n\n📝 DRAFT e rekhe dilam. Oi time e ami toke photo + caption + gaan sob pathiye debo.\n\nEbar kotay post korbo?\n'EKHON' / '10 PM' / 'KAL 10 AM' likh.")
        return
    if state == "waiting_time":
        if text in ["cancel","batil"]:
            context.application.bot_data[f"state_{chat_id}"] = "caption_ready"
            await update.message.reply_text("Thik ache, cancel kore dilam.")
            return
        delay = parse_time(text)
        if delay is None:
            await update.message.reply_text("Time ta bujhlam na. Erom kore lekho: '6 PM' / '10 PM' / 'KAL 10 AM' / 'EKHON'")
            return
        song = context.application.bot_data.get(f"song_{chat_id}", "")
        if delay == 0:
            caption = context.application.bot_data.get(f"caption_{chat_id}", "Roopkatha")
            album = context.application.bot_data.get(f"last_album_{chat_id}", [])
            if song:
                await update.message.reply_text("📝 DRAFT READY! Ekhoni post kor:")
                for b in album: await update.message.reply_photo(photo=io.BytesIO(b))
                await update.message.reply_text(f"🎵 Gaan: {song}\n\n📝 Caption:\n{caption}")
            else:
                result = post_carousel_to_instagram(album, caption)
                await update.message.reply_text(f"✅ Auto post hoye geche!\n{result}")
            context.application.bot_data[f"state_{chat_id}"] = "done"
            return
        asyncio.create_task(scheduled_post(chat_id, context, delay, text))
        context.application.bot_data[f"state_{chat_id}"] = "scheduled"
        if song:
            await update.message.reply_text(f"✅ DRAFT save hoye gelo! 📝\n{text} e ami toke photo + caption + gaan pathiye debo.\n🎵 Gaan: {song}\n\nCancel korte 'CANCEL' likh.")
        else:
            await update.message.reply_text(f"✅ Done! {text} e auto post hoye jabe. ⏰\n\nCancel korte 'CANCEL' likh.")
        return
    if text == "ha":
        caption = context.application.bot_data.get(f"caption_{chat_id}", "")
        album = context.application.bot_data.get(f"last_album_{chat_id}", [])
        if not caption:
            await update.message.reply_text("Age ekta photo pathao."); return
        context.application.bot_data[f"state_{chat_id}"] = "preview"
        await update.message.reply_text(f"🔍 FINAL PREVIEW:\n\n📸 Photo: {len(album)} ta\n\n📝 Caption:\n{caption}\n\nSob thik ache? Tahole 'FINAL' likh.\nBodlate chaile 'ABAR' likh.")
        return
    if text == "final":
        context.application.bot_data[f"state_{chat_id}"] = "waiting_song"
        await update.message.reply_text("Perfect! 🔥\n\n🎵 Gaan lagbe?\n\nGaan er naam ta likh - jemon 'Tum Se Hi'\nGaan lagbe na hole 'NO SONG' likh.")
        return
    if text == "abar":
        last_album = context.application.bot_data.get(f"last_album_{chat_id}", [])
        if not last_album:
            await update.message.reply_text("Age ekta photo pathao."); return
        await update.message.reply_text("Thik ache, oi photo gulo diye arekta notun caption banacchi... ✨")
        imgs = []
        for b in last_album:
            img = Image.open(io.BytesIO(b)); img.thumbnail((768,768)); imgs.append(img)
        caption = await make_caption(imgs)
        context.application.bot_data[f"caption_{chat_id}"] = caption
        context.application.bot_data[f"state_{chat_id}"] = "caption_ready"
        await update.message.reply_text(f"Notun caption! 👇\n\n{caption}\n\nPochondo? 'HA' likh.\nAbar bodlate 'ABAR' likh.")
        return
    await update.message.reply_text("Photo pathao, ami caption baniye debo.")

app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))
print("Bot cholche...")
app.run_polling()