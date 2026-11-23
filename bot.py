import os
import re
import time
import asyncio
import subprocess
from typing import NamedTuple, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors import FloodWait, ChannelPrivate, ChatAdminRequired, ChannelInvalid
from config import Config
from database import db
from downloader import download_telegram_file
from mega_cli import MegaCLI
from progress import human_bytes, time_formatter

# ---- Initialize Pyrogram Bot ---- #
app = Client(
    "tg_to_mega_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    if Config.OWNER_ID == 0:
        return True
    return user_id == Config.OWNER_ID


# ---- Queue Management System ---- #
class QueueItem(NamedTuple):
    client: Client
    message: Message
    status_msg: Message
    file_name: str
    file_size: int
    queue_num: int


upload_queue: asyncio.Queue = asyncio.Queue()
_worker_task: Optional[asyncio.Task] = None
_current_item: Optional[QueueItem] = None
_task_counter: int = 0


def ensure_worker():
    """Ensure the background queue consumer is running."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(queue_worker())


async def queue_worker():
    """Processes upload tasks one by one sequentially from the queue."""
    global _current_item
    print("👷 Queue worker started.")

    while True:
        try:
            item: QueueItem = await upload_queue.get()
            _current_item = item

            client = item.client
            message = item.message
            status_msg = item.status_msg
            file_name = item.file_name
            file_size = item.file_size
            queue_num = item.queue_num

            remaining = upload_queue.qsize()
            queue_info = f" [Remaining in queue: {remaining}]" if remaining > 0 else ""
            print(f"🎬 Processing Task #{queue_num}: {file_name} ({human_bytes(file_size)}){queue_info}")

            await status_msg.edit_text(
                f"🔍 **Processing:** `{file_name}`\n"
                f"📦 **Size:** `{human_bytes(file_size)}`\n"
                f"⏳ Initializing download from Telegram...",
            )

            # Step 1: Download from Telegram to local disk with live progress
            file_path = await download_telegram_file(client, message, status_msg)
            if not file_path or not os.path.exists(file_path):
                print(f"❌ Download failed for: {file_name}")
                upload_queue.task_done()
                _current_item = None
                continue

            print(f"✅ Downloaded to: {file_path}")

            # Step 2: Determine target folder on Mega
            user_info = db.get_user(message.from_user.id)
            custom_folder = user_info.get("custom_folder", "").strip()
            base_folder = Config.MEGA_FOLDER
            if custom_folder:
                target_folder = f"{base_folder.rstrip('/')}/{custom_folder}"
            else:
                target_folder = base_folder

            await status_msg.edit_text(
                f"📤 **Uploading to Mega.nz...**\n\n"
                f"📄 **File:** `{file_name}`\n"
                f"📦 **Size:** `{human_bytes(file_size)}`\n"
                f"📂 **Folder:** `{target_folder}`\n\n"
                "⚡ Transferring via official MEGAcmd engine..."
            )

            start_upload_time = time.time()
            print(f"🚀 Uploading to Mega folder: {target_folder}...")

            # Step 3: Upload via official MEGAcmd (with auto-deduplication)
            success, mega_link, msg, final_file_name = await MegaCLI.upload_file(file_path, target_folder)
            if final_file_name:
                file_name = final_file_name

            # Step 4: Remove local temporary file immediately to free Colab disk
            try:
                dir_name = os.path.dirname(file_path)
                actual_path = os.path.join(dir_name, file_name)
                if os.path.exists(actual_path):
                    os.remove(actual_path)
                    print(f"🗑️ Removed temp file: {actual_path}")
                elif os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

            # Step 5: Send response
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("☁️ Open Mega Drive", url="https://mega.nz/fm")]]
            )

            if success:
                elapsed = time.time() - start_upload_time
                avg_speed = human_bytes(int(file_size / elapsed)) if elapsed > 0 else "N/A"
                print(f"🎉 Task #{queue_num} finished! Saved to {target_folder}/{file_name}")

                db.update_stats(message.from_user.id, file_size)
                db.save_upload(message.from_user.id, file_name, file_size, f"{target_folder}/{file_name}")

                rem = upload_queue.qsize()
                rem_text = f"\n\n🔄 **Queue Remaining:** `{rem}` file(s)" if rem > 0 else ""

                success_text = (
                    "🎉 **Successfully Uploaded to Mega.nz!**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"📦 **Size:** `{human_bytes(file_size)}`\n"
                    f"📂 **Folder:** `{target_folder}`\n"
                    f"⚡ **Speed:** `{avg_speed}/s`\n"
                    f"⏱️ **Time:** `{time_formatter(elapsed)}`\n\n"
                    f"☁️ **Status:** Saved to your Mega.nz Cloud Drive{rem_text}"
                )
                await status_msg.edit_text(success_text, reply_markup=keyboard)
            else:
                print(f"❌ Task #{queue_num} upload failed: {msg}")
                await status_msg.edit_text(f"❌ **Upload Failed:** `{msg}`")

            upload_queue.task_done()
            _current_item = None
            await asyncio.sleep(1)  # Brief pause between tasks for system stability

        except Exception as e:
            print(f"⚠️ Queue Worker Error: {e}")
            if _current_item and _current_item.status_msg:
                try:
                    await _current_item.status_msg.edit_text(f"❌ **Error:** `{str(e)}`")
                except Exception:
                    pass
            upload_queue.task_done()
            _current_item = None
            await asyncio.sleep(1)


# ---- UI Keyboards ---- #
def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📁 Set Folder", callback_data="btn_folder"),
                InlineKeyboardButton("📊 Stats", callback_data="btn_status"),
            ],
            [
                InlineKeyboardButton("💾 Storage", callback_data="btn_storage"),
                InlineKeyboardButton("🔄 Queue", callback_data="btn_queue"),
            ],
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="btn_help"),
                InlineKeyboardButton("☁️ Open Mega.nz", url="https://mega.nz/fm"),
            ],
        ]
    )


def back_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="btn_menu")]]
    )


# ---- /start Command ---- #
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Friend"
    print(f"📩 /start received from {user_name} (ID: {user_id})")

    if not is_authorized(user_id):
        print(f"⛔ Access Denied for User ID: {user_id} (Configured OWNER_ID: {Config.OWNER_ID})")
        await message.reply_text(
            f"⛔ **Access Denied:** You are not authorized.\n\n"
            f"Your Telegram User ID is: `{user_id}`\n\n"
            f"Set `OWNER_ID = {user_id}` in your Colab config to allow yourself!"
        )
        return

    text = (
        f"👋 **Hello {user_name}!**\n\n"
        "⚡ **Mega.nz Telegram Uploader (Batch & Queue Edition)**\n\n"
        "I can upload any file, video, photo, or document from Telegram "
        "directly to your **Mega.nz** cloud storage!\n\n"
        "✨ **Features:**\n"
        "• 🎥 **Batch Forwarding**: Select and forward multiple videos at once!\n"
        "• ⚡ **Sequential Queue**: Files are queued and uploaded one-by-one safely\n"
        "• 🔗 **Link Range Support**: `/batch <link>-<range>`\n"
        "• 🛡️ **Duplicate Protection**: Prevents overwriting with automatic timestamps\n"
        "• 📊 **Live Progress Bar**: Speed, percentage, transferred size & ETA\n"
        "• 📁 **Custom Folders**: `/setfolder <name>`\n"
        "• 💾 **20 GB Free Storage** on Mega.nz\n\n"
        "Forward single or multiple files to get started! 🚀"
    )
    await message.reply_text(text, reply_markup=main_keyboard())


# ---- /help Command ---- #
@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    text = (
        "📖 **How to Use:**\n\n"
        "1️⃣ **Batch Forwarding (Recommended):**\n"
        "• Select multiple files/videos in any channel or chat.\n"
        "• Forward them all at once to this bot!\n"
        "• The bot queues all files and uploads them **one by one** automatically without errors.\n\n"
        "2️⃣ **Batch by Link Range (`/batch`):**\n"
        "• Send: `/batch https://t.me/c/3930712197/96-100`\n"
        "• Or: `/batch https://t.me/mychannel/10-25`\n"
        "*(Note: For private channels, the bot must be an admin/member, or you can simply forward the files directly!)*\n\n"
        "3️⃣ **Manage Folders:**\n"
        "• `/setfolder Movies` → Uploads go to 'Movies' subfolder on Mega.\n"
        "• `/setfolder default` → Reset to default folder (`/TelegramUploads`).\n\n"
        "4️⃣ **Queue Commands:**\n"
        "• `/queue` → Check currently uploading file & pending queue.\n"
        "• `/clearqueue` → Clear all pending items from the queue.\n\n"
        "5️⃣ **Storage & Stats:**\n"
        "• `/storage` → Check Mega.nz account storage (used/free/total).\n"
        "• `/status` → Your upload stats.\n"
        "• `/recent` → Last 10 uploaded files."
    )
    await message.reply_text(text, reply_markup=back_keyboard())


# ---- /queue Command ---- #
@app.on_message(filters.command("queue") & filters.private)
async def queue_status_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    qsize = upload_queue.qsize()
    if _current_item is None and qsize == 0:
        await message.reply_text("📭 **Queue is currently empty.** No uploads in progress.")
        return

    text = "🔄 **Current Queue Status:**\n\n"
    if _current_item:
        text += (
            f"▶️ **Currently Uploading:**\n"
            f"📄 `{_current_item.file_name}`\n"
            f"📦 `{human_bytes(_current_item.file_size)}`\n\n"
        )
    text += f"⏳ **Files Waiting in Queue:** `{qsize}`\n"
    await message.reply_text(text, reply_markup=back_keyboard())


# ---- /clearqueue Command ---- #
@app.on_message(filters.command("clearqueue") & filters.private)
async def clearqueue_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    count = 0
    while not upload_queue.empty():
        try:
            item = upload_queue.get_nowait()
            upload_queue.task_done()
            try:
                await item.status_msg.edit_text("🚫 **Upload cancelled from queue.**")
            except Exception:
                pass
            count += 1
        except Exception:
            break

    await message.reply_text(f"🗑️ **Cleared `{count}` pending file(s) from the queue.**")


# ---- /setfolder Command ---- #
@app.on_message(filters.command("setfolder") & filters.private)
async def setfolder_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        user_info = db.get_user(message.from_user.id)
        current = user_info.get("custom_folder") or "Default (TelegramUploads)"
        await message.reply_text(
            f"📁 **Current Folder:** `{current}`\n\n"
            "To change folder:\n"
            "`/setfolder FolderName`\n\n"
            "To reset to default:\n"
            "`/setfolder default`"
        )
        return

    folder_name = args[1].strip()
    folder_name = folder_name.replace("..", "").replace("\\", "/")
    folder_name = "/".join(p for p in folder_name.split("/") if p and p != ".")

    if folder_name.lower() == "default" or not folder_name:
        db.set_custom_folder(message.from_user.id, "")
        await message.reply_text("✅ Target folder reset to **Default (TelegramUploads)**.")
    else:
        db.set_custom_folder(message.from_user.id, folder_name)
        await message.reply_text(f"✅ Target folder set to: **`{folder_name}`**")


# ---- /status Command ---- #
@app.on_message(filters.command("status") & filters.private)
async def status_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    user_info = db.get_user(message.from_user.id)
    total_bytes = user_info.get("total_uploaded_bytes", 0)
    total_files = user_info.get("total_files", 0)
    custom_folder = user_info.get("custom_folder") or "Default"

    text = (
        "📊 **Your Upload Stats:**\n\n"
        f"📂 **Target Folder:** `{custom_folder}`\n"
        f"📁 **Files Uploaded:** `{total_files}`\n"
        f"📦 **Total Data Uploaded:** `{human_bytes(total_bytes)}`"
    )
    await message.reply_text(text, reply_markup=back_keyboard())


# ---- /storage Command ---- #
@app.on_message(filters.command("storage") & filters.private)
async def storage_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    status_msg = await message.reply_text("🔍 **Checking Mega.nz storage...**")
    stats = await MegaCLI.get_storage()
    text = (
        "💾 **Mega.nz Storage Status:**\n\n"
        f"📊 **Total:** `{stats.get('total', 'N/A')}`\n"
        f"📦 **Used:** `{stats.get('used', 'N/A')}`\n"
        f"✅ **Free:** `{stats.get('free', 'N/A')}`"
    )
    await status_msg.edit_text(text, reply_markup=back_keyboard())


# ---- /recent Command ---- #
@app.on_message(filters.command("recent") & filters.private)
async def recent_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    uploads = db.get_recent_uploads(message.from_user.id, limit=10)
    if not uploads:
        await message.reply_text("📭 **No uploads yet.** Send me a file to get started!")
        return

    text = "📋 **Recent Uploads:**\n\n"
    for i, up in enumerate(uploads, 1):
        name = up["file_name"]
        size = human_bytes(up["file_size"])
        link = up["mega_link"]
        text += f"{i}. `{name}` ({size})\n   🔗 {link}\n\n"

    await message.reply_text(text, reply_markup=back_keyboard())


# ---- Callback Query Handler ---- #
@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data

    if data == "btn_menu":
        await query.message.edit_text(
            "⚡ **Mega.nz Telegram Uploader**\n\nChoose an option:",
            reply_markup=main_keyboard(),
        )
    elif data == "btn_help":
        await query.message.edit_text(
            "📖 **Quick Help:**\n\n"
            "• **Batch Forward:** Select multiple videos & forward to bot.\n"
            "• **Range Upload:** `/batch https://t.me/c/.../96-100`\n"
            "• **Set Folder:** `/setfolder FolderName`\n"
            "• **Check Queue:** `/queue`\n"
            "• **Check Storage:** `/storage`",
            reply_markup=back_keyboard(),
        )
    elif data == "btn_folder":
        user_info = db.get_user(query.from_user.id)
        current = user_info.get("custom_folder") or "Default"
        await query.message.edit_text(
            f"📁 **Current Folder:** `{current}`\n\n"
            "To change folder, type in chat:\n"
            "`/setfolder FolderName`",
            reply_markup=back_keyboard(),
        )
    elif data == "btn_status":
        user_info = db.get_user(query.from_user.id)
        total_bytes = user_info.get("total_uploaded_bytes", 0)
        total_files = user_info.get("total_files", 0)
        await query.message.edit_text(
            f"📊 **Your Stats:**\n\n"
            f"• Total Files: `{total_files}`\n"
            f"• Total Uploaded: `{human_bytes(total_bytes)}`",
            reply_markup=back_keyboard(),
        )
    elif data == "btn_storage":
        stats = await MegaCLI.get_storage()
        await query.message.edit_text(
            f"💾 **Mega.nz Storage:**\n\n"
            f"📊 Total: `{stats.get('total', 'N/A')}`\n"
            f"📦 Used: `{stats.get('used', 'N/A')}`\n"
            f"✅ Free: `{stats.get('free', 'N/A')}`",
            reply_markup=back_keyboard(),
        )
    elif data == "btn_queue":
        qsize = upload_queue.qsize()
        text = "🔄 **Current Queue Status:**\n\n"
        if _current_item:
            text += (
                f"▶️ **Currently Uploading:**\n"
                f"📄 `{_current_item.file_name}`\n"
                f"📦 `{human_bytes(_current_item.file_size)}`\n\n"
            )
        text += f"⏳ **Files Waiting in Queue:** `{qsize}`\n"
        await query.message.edit_text(text, reply_markup=back_keyboard())


# ---- Helper Function to Queue a Media Message ---- #
async def enqueue_media_message(client: Client, message: Message, custom_title: Optional[str] = None):
    """Extracts media details and places the task into the upload queue."""
    global _task_counter

    media = (
        message.document
        or message.video
        or message.audio
        or message.animation
        or message.voice
        or message.video_note
    )

    if message.photo:
        file_name = f"Photo_{int(time.time())}.jpg"
        file_size = message.photo.file_size
    elif media:
        file_name = custom_title or getattr(media, "file_name", None) or f"File_{int(time.time())}"
        file_size = getattr(media, "file_size", 0)
    else:
        return False

    if file_size == 0:
        return False

    _task_counter += 1
    task_num = _task_counter
    pos = upload_queue.qsize() + (1 if _current_item else 0)

    if pos == 0:
        status_msg = await message.reply_text(
            f"⏳ **Starting:** `{file_name}`\n📦 **Size:** `{human_bytes(file_size)}`",
            quote=True,
        )
    else:
        status_msg = await message.reply_text(
            f"📥 **Added to Queue (Position #{pos + 1}):**\n"
            f"📄 `{file_name}`\n"
            f"📦 **Size:** `{human_bytes(file_size)}`\n"
            "⏳ Will process automatically in sequence...",
            quote=True,
        )

    await upload_queue.put(
        QueueItem(
            client=client,
            message=message,
            status_msg=status_msg,
            file_name=file_name,
            file_size=file_size,
            queue_num=task_num,
        )
    )
    ensure_worker()
    return True


# ---- Telegram Media Handler (Single & Batch Forwarding) ---- #
@app.on_message(
    filters.private
    & (
        filters.document
        | filters.video
        | filters.audio
        | filters.photo
        | filters.animation
        | filters.voice
        | filters.video_note
    )
)
async def telegram_media_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        print(f"⛔ Access Denied for media from {user_id}")
        await message.reply_text(
            f"⛔ **Access Denied:** Your User ID `{user_id}` is not authorized."
        )
        return

    await enqueue_media_message(client, message)


# ---- /batch Link Range Handler ---- #
# Supports:
# /batch https://t.me/c/3930712197/96-100
# /batch https://t.me/channel_name/10-20
# Or directly sending the link range
@app.on_message(
    filters.private
    & (filters.command("batch") | filters.regex(r"https?://t\.me/(?:c/(\d+)|([a-zA-Z0-9_]+))/(\d+)(?:-(\d+))?"))
)
async def batch_link_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        return

    text = message.text.strip()
    match = re.search(r"https?://t\.me/(?:c/(\d+)|([a-zA-Z0-9_]+))/(\d+)(?:-(\d+))?", text)
    if not match:
        await message.reply_text(
            "⚠️ **Usage:**\n"
            "`/batch https://t.me/c/3930712197/96-100`\n"
            "or `/batch https://t.me/channel_username/10-20`"
        )
        return

    priv_cid, pub_cid, start_id_str, end_id_str = match.groups()

    # Determine chat ID
    if priv_cid:
        chat_id = int(f"-100{priv_cid}")
    else:
        chat_id = pub_cid

    start_id = int(start_id_str)
    end_id = int(end_id_str) if end_id_str else start_id

    if end_id < start_id:
        start_id, end_id = end_id, start_id

    total_msgs = end_id - start_id + 1
    if total_msgs > 100:
        await message.reply_text("⚠️ Maximum 100 messages can be batched in a single range at once.")
        return

    fetch_msg = await message.reply_text(
        f"🔍 **Fetching {total_msgs} message(s) from range `{start_id}` to `{end_id}`...**"
    )

    try:
        msg_ids = list(range(start_id, end_id + 1))
        fetched_messages = await client.get_messages(chat_id, msg_ids)

        if not isinstance(fetched_messages, list):
            fetched_messages = [fetched_messages]

        queued_count = 0
        for msg in fetched_messages:
            if msg and (msg.document or msg.video or msg.audio or msg.photo):
                ok = await enqueue_media_message(client, msg)
                if ok:
                    queued_count += 1

        if queued_count > 0:
            await fetch_msg.edit_text(
                f"✅ **Queued {queued_count} media file(s) successfully!**\n"
                "⚡ They will be downloaded and uploaded to Mega.nz one by one."
            )
        else:
            await fetch_msg.edit_text("ℹ️ No media files found in the specified message range.")

    except (ChannelPrivate, ChatAdminRequired, ChannelInvalid):
        await fetch_msg.edit_text(
            "⚠️ **Cannot access this private channel directly.**\n\n"
            "Telegram bots cannot read messages from private channels unless added as an admin/member.\n\n"
            "💡 **Easy Solution:**\n"
            "Just open that channel, **select all the videos** you want, and **FORWARD** them all at once to this bot!\n\n"
            "The bot will automatically queue all of them and upload them one by one without any errors!"
        )
    except Exception as e:
        await fetch_msg.edit_text(f"❌ **Error fetching batch:** `{str(e)}`")


# ---- Start/Help fallback for non-media text ---- #
@app.on_message(
    filters.private
    & filters.text
    & ~filters.command(["start", "help", "status", "storage", "setfolder", "recent", "queue", "clearqueue", "batch"])
)
async def text_fallback(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        await message.reply_text(
            f"⛔ **Access Denied:** Your User ID `{user_id}` is not authorized.\n"
            f"Set `OWNER_ID = {user_id}` in Colab."
        )
        return

    await message.reply_text(
        "📎 **Batch Upload Ready!**\n\n"
        "• **Forward Multiple Files**: Select multiple files in any chat and forward them here.\n"
        "• **Batch Link Range**: `/batch https://t.me/c/.../96-100`\n"
        "• **Check Queue**: `/queue`\n\n"
        "Type `/help` for all commands.",
    )


# ---- Main Entry Point ---- #
if __name__ == "__main__":
    print("🚀 Mega.nz Telegram Bot is starting (Queue & Batch Edition)...")
    print(f"📂 Target Mega folder: {Config.MEGA_FOLDER}")
    if Config.OWNER_ID:
        print(f"🔒 Restricted to user ID: {Config.OWNER_ID}")
    else:
        print("⚠️ No OWNER_ID set — bot is open to all users!")

    try:
        check = subprocess.run(["mega-whoami"], capture_output=True, text=True)
        if "@" in check.stdout:
            print(f"✅ MEGAcmd verified: {check.stdout.strip()}")
        else:
            print(f"⚠️ MEGAcmd status: {check.stdout.strip() or check.stderr.strip()}")
    except Exception as e:
        print(f"⚠️ MEGAcmd check error: {e}")

    print("🤖 Starting Pyrogram Telegram Client via app.run()...")
    app.run()
