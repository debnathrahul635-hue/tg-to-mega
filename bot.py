import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from config import Config
from database import db
from mega import Mega
from tg_streamer import TelegramFile
from progress import human_bytes, time_formatter, progress_callback, create_progress_bar

# ---- Initialize Bot ---- #
app = Client(
    "tg_to_mega_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True,
)

# Global Mega client (initialized on first use)
_mega_client: Mega = None
_mega_lock = asyncio.Lock()


async def get_mega() -> Mega:
    """Get or create the authenticated Mega client."""
    global _mega_client
    async with _mega_lock:
        if _mega_client is None:
            _mega_client = Mega()
            success = await _mega_client.login(Config.MEGA_EMAIL, Config.MEGA_PASSWORD)
            if not success:
                _mega_client = None
                raise Exception("Failed to login to Mega.nz. Check your email and password.")
            print("✅ Logged into Mega.nz successfully!")
        return _mega_client


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    if Config.OWNER_ID == 0:
        return True
    return user_id == Config.OWNER_ID


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
                InlineKeyboardButton("ℹ️ Help", callback_data="btn_help"),
            ],
            [
                InlineKeyboardButton(
                    "☁️ Open Mega.nz", url="https://mega.nz/fm"
                ),
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
    if not is_authorized(message.from_user.id):
        await message.reply_text("⛔ **Access Denied:** You are not authorized to use this bot.")
        return

    user_name = message.from_user.first_name or "Friend"
    text = (
        f"👋 **Hello {user_name}!**\n\n"
        "⚡ **Mega.nz Telegram Uploader**\n\n"
        "I can upload any file, video, photo, or document from Telegram "
        "directly to your **Mega.nz** cloud storage!\n\n"
        "✨ **Features:**\n"
        "• 🎥 Videos, 📄 Documents, 🎵 Music, 🖼️ Photos\n"
        "• ⚡ Zero-disk streaming (Telegram → Mega, no temp files)\n"
        "• 📊 Live progress bar with speed & ETA\n"
        "• 📁 Custom folder support\n"
        "• 🔗 Direct shareable Mega.nz links\n"
        "• 💾 20 GB free Mega storage\n\n"
        "Just send me any file to get started! 🚀"
    )
    await message.reply_text(text, reply_markup=main_keyboard())


# ---- /help Command ---- #
@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return

    text = (
        "📖 **How to Use:**\n\n"
        "1️⃣ **Upload Telegram Files:**\n"
        "• Send any Video, Photo, Audio, or Document.\n"
        "• Bot will stream it directly to Mega.nz with a live progress bar.\n"
        "• You'll get a shareable Mega.nz link!\n\n"
        "2️⃣ **Manage Folders:**\n"
        "• `/setfolder Movies` → Uploads go to 'Movies' subfolder.\n"
        "• `/setfolder default` → Reset to default folder.\n\n"
        "3️⃣ **Check Status:**\n"
        "• `/status` → Your upload stats.\n"
        "• `/storage` → Mega.nz storage info.\n"
        "• `/recent` → Last 10 uploaded files with links.\n\n"
        "4️⃣ **Limits:**\n"
        "• Telegram bot files: up to 2 GB (via Pyrogram MTProto).\n"
        "• Mega free storage: 20 GB total."
    )
    await message.reply_text(text, reply_markup=back_keyboard())


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

    # Sanitize: remove path traversal attempts
    folder_name = folder_name.replace("..", "").replace("\\", "/")
    folder_name = "/".join(p for p in folder_name.split("/") if p and p != ".")

    if folder_name.lower() == "default" or not folder_name:
        db.set_custom_folder(message.from_user.id, "")
        await message.reply_text("✅ Target folder reset to **Default (TelegramUploads)**.")
    else:
        db.set_custom_folder(message.from_user.id, folder_name)
        await message.reply_text(f"✅ Upload folder set to: **`{folder_name}`**")


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

    try:
        mega = await get_mega()
        info = await mega.get_storage_info()
        total = info["total"]
        used = info["used"]
        free = info["free"]

        bar = create_progress_bar(used, total, length=14)
        pct = (used / total * 100) if total > 0 else 0

        text = (
            "💾 **Mega.nz Storage Info:**\n\n"
            f"`[{bar}]` **{pct:.1f}% used**\n\n"
            f"📦 **Used:** `{human_bytes(used)}`\n"
            f"✅ **Free:** `{human_bytes(free)}`\n"
            f"📊 **Total:** `{human_bytes(total)}`"
        )
        await status_msg.edit_text(text, reply_markup=back_keyboard())
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** `{str(e)}`")


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
            "• **Upload File:** Send any video, photo, audio or document.\n"
            "• **Set Folder:** `/setfolder FolderName`\n"
            "• **Check Storage:** `/storage`\n"
            "• **Recent Files:** `/recent`",
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
        await query.message.edit_text("🔍 **Checking Mega.nz storage...**")
        try:
            mega = await get_mega()
            info = await mega.get_storage_info()
            bar = create_progress_bar(info["used"], info["total"], length=14)
            pct = (info["used"] / info["total"] * 100) if info["total"] > 0 else 0
            await query.message.edit_text(
                f"💾 **Mega.nz Storage:**\n\n"
                f"`[{bar}]` **{pct:.1f}% used**\n\n"
                f"📦 Used: `{human_bytes(info['used'])}`\n"
                f"✅ Free: `{human_bytes(info['free'])}`\n"
                f"📊 Total: `{human_bytes(info['total'])}`",
                reply_markup=back_keyboard(),
            )
        except Exception as e:
            await query.message.edit_text(
                f"❌ **Error:** `{str(e)}`", reply_markup=back_keyboard()
            )


# ---- Telegram Media Handler (Core Upload Logic) ---- #
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
    if not is_authorized(message.from_user.id):
        await message.reply_text("⛔ Access Denied.")
        return

    # Extract media details
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
        file_id = message.photo.file_id
    elif media:
        file_name = getattr(media, "file_name", None) or f"File_{int(time.time())}"
        file_size = getattr(media, "file_size", 0)
        file_id = media.file_id
    else:
        await message.reply_text("❌ Could not detect file.")
        return

    if file_size == 0:
        await message.reply_text("❌ **Error:** File size is 0 bytes.")
        return

    status_msg = await message.reply_text(
        f"🔍 **Processing:** `{file_name}`\n"
        f"📦 **Size:** `{human_bytes(file_size)}`\n"
        f"⏳ Connecting to Mega.nz...",
        quote=True,
    )

    try:
        # Step 1: Get Mega client
        mega = await get_mega()

        # Step 2: Determine target folder
        user_info = db.get_user(message.from_user.id)
        custom_folder = user_info.get("custom_folder", "").strip()

        base_folder = Config.MEGA_FOLDER
        if custom_folder:
            target_folder = f"{base_folder.rstrip('/')}/{custom_folder}"
        else:
            target_folder = base_folder

        await status_msg.edit_text(
            f"📁 **Setting up folder:** `{target_folder}`\n"
            f"⏳ Preparing upload..."
        )

        folder_id = await mega.find_or_create_folder(target_folder)

        # Step 3: Initialize Telegram file streamer
        tg_file = TelegramFile(client, file_id, file_size)
        await tg_file.start_buffer()

        start_time = time.time()

        # Step 4: Progress callback for Mega upload
        async def upload_progress(current, total):
            await progress_callback(
                current, total, status_msg, start_time, "📤 Uploading to Mega.nz"
            )

        # Step 5: Stream upload to Mega
        mega_link = await mega.upload_from_stream(
            read_func=tg_file.read,
            file_size=file_size,
            filename=file_name,
            dest_folder_id=folder_id,
            callback=upload_progress,
        )

        if mega_link:
            # Save to database
            db.update_stats(message.from_user.id, file_size)
            db.save_upload(message.from_user.id, file_name, file_size, mega_link)

            elapsed = time.time() - start_time
            avg_speed = human_bytes(int(file_size / elapsed)) if elapsed > 0 else "N/A"

            success_text = (
                "🎉 **Successfully Uploaded to Mega.nz!**\n\n"
                f"📄 **File:** `{file_name}`\n"
                f"📦 **Size:** `{human_bytes(file_size)}`\n"
                f"📂 **Folder:** `{target_folder}`\n"
                f"⚡ **Avg Speed:** `{avg_speed}/s`\n"
                f"⏱️ **Time:** `{time_formatter(elapsed)}`\n\n"
                f"🔗 **Download Link:**\n`{mega_link}`"
            )
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("📥 Open Link", url=mega_link),
                        InlineKeyboardButton("☁️ Open Mega", url="https://mega.nz/fm"),
                    ]
                ]
            )
            await status_msg.edit_text(success_text, reply_markup=keyboard)
        else:
            await status_msg.edit_text("❌ **Upload Failed:** Could not complete upload to Mega.nz.")

    except Exception as e:
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        await status_msg.edit_text(f"❌ **Error:** `{error_msg}`")


# ---- Start/Help fallback for non-media text ---- #
@app.on_message(filters.private & filters.text & ~filters.command(["start", "help", "status", "storage", "setfolder", "recent"]))
async def text_fallback(client: Client, message: Message):
    if not is_authorized(message.from_user.id):
        return
    await message.reply_text(
        "📎 **Send me a file** (video, photo, document, audio) and I'll upload it to Mega.nz!\n\n"
        "Type `/help` for all commands.",
    )


# ---- Main Entry Point ---- #
if __name__ == "__main__":
    print("🚀 Mega.nz Telegram Bot is starting...")
    print(f"📂 Target Mega folder: {Config.MEGA_FOLDER}")
    if Config.OWNER_ID:
        print(f"🔒 Restricted to user ID: {Config.OWNER_ID}")
    else:
        print("⚠️ No OWNER_ID set — bot is open to all users!")
    app.run()
