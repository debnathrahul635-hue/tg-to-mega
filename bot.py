import os
import time
import subprocess
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from config import Config
from database import db
from downloader import download_telegram_file
from mega_cli import MegaCLI
from progress import human_bytes, time_formatter

# ---- Initialize Pyrogram Bot (Identical to GDrive Bot) ---- #
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
        "⚡ **Mega.nz Telegram Uploader (Official MEGAcmd Engine)**\n\n"
        "I can upload any file, video, photo, or document from Telegram "
        "directly to your **Mega.nz** cloud storage!\n\n"
        "✨ **Features:**\n"
        "• 🎥 Videos, 📄 Documents, 🎵 Music, 🖼️ Photos\n"
        "• ⚡ Official MEGAcmd engine — fast, stable, no API limits\n"
        "• 📊 Live progress bar with speed & ETA during download\n"
        "• 📁 Custom folder support via `/setfolder`\n"
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
        "• Send or forward any Video, Photo, Audio, or Document.\n"
        "• The bot downloads it with a live progress bar, uploads it to Mega.nz, and sends you a shareable link.\n\n"
        "2️⃣ **Manage Folders:**\n"
        "• `/setfolder Movies` → Uploads go to 'Movies' subfolder on Mega.\n"
        "• `/setfolder default` → Reset to default folder.\n\n"
        "3️⃣ **Check Status:**\n"
        "• `/status` → Your upload stats.\n"
        "• `/storage` → Mega.nz account storage.\n"
        "• `/recent` → Last 10 uploaded files with links.\n\n"
        "4️⃣ **Limits:**\n"
        "• Telegram files: up to 2 GB per file.\n"
        "• Mega.nz free storage: 20 GB total."
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
        stats = await MegaCLI.get_storage()
        await query.message.edit_text(
            f"💾 **Mega.nz Storage:**\n\n"
            f"📊 Total: `{stats.get('total', 'N/A')}`\n"
            f"📦 Used: `{stats.get('used', 'N/A')}`\n"
            f"✅ Free: `{stats.get('free', 'N/A')}`",
            reply_markup=back_keyboard(),
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
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Friend"
    print(f"📦 Media received from {user_name} (ID: {user_id})")

    if not is_authorized(user_id):
        print(f"⛔ Access Denied for media from {user_id}")
        await message.reply_text(
            f"⛔ **Access Denied:** Your User ID `{user_id}` is not authorized."
        )
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
    elif media:
        file_name = getattr(media, "file_name", None) or f"File_{int(time.time())}"
        file_size = getattr(media, "file_size", 0)
    else:
        file_name = f"File_{int(time.time())}"
        file_size = 0

    if file_size == 0:
        await message.reply_text("❌ **Error:** File size is 0 bytes.")
        return

    print(f"📥 Starting download: {file_name} ({human_bytes(file_size)})")

    status_msg = await message.reply_text(
        f"🔍 **Processing:** `{file_name}`\n"
        f"📦 **Size:** `{human_bytes(file_size)}`\n"
        "⏳ Initializing download...",
        quote=True,
    )

    # Step 1: Download from Telegram to local disk with live progress
    file_path = await download_telegram_file(client, message, status_msg)
    if not file_path or not os.path.exists(file_path):
        print("❌ Download failed or cancelled.")
        return

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

    # Step 3: Upload via official MEGAcmd
    success, mega_link, msg = await MegaCLI.upload_file(file_path, target_folder)

    # Step 4: Remove local temporary file
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass

        # Step 5: Send response
        buttons = []
        if mega_link and ("mega.nz/file" in mega_link or "mega.nz/#" in mega_link):
            buttons.append(InlineKeyboardButton("📥 Download Link", url=mega_link))
        buttons.append(InlineKeyboardButton("☁️ Open Mega Drive", url="https://mega.nz/fm"))
        keyboard = InlineKeyboardMarkup([buttons])

        if success:
            elapsed = time.time() - start_upload_time
            avg_speed = human_bytes(int(file_size / elapsed)) if elapsed > 0 else "N/A"
            print(f"🎉 Upload successful! Link: {mega_link}")

            # Update database stats
            db.update_stats(message.from_user.id, file_size)
            db.save_upload(message.from_user.id, file_name, file_size, mega_link or "N/A")

            if "mega.nz/file" in mega_link or "mega.nz/#" in mega_link:
                location_text = f"🔗 **Download Link:**\n`{mega_link}`"
            else:
                location_text = f"☁️ **Saved to Mega:** `/TelegramUploads/{file_name}`"

            success_text = (
                "🎉 **Successfully Uploaded to Mega.nz!**\n\n"
                f"📄 **File:** `{file_name}`\n"
                f"📦 **Size:** `{human_bytes(file_size)}`\n"
                f"📂 **Folder:** `{target_folder}`\n"
                f"⚡ **Upload Speed:** `{avg_speed}/s`\n"
                f"⏱️ **Upload Time:** `{time_formatter(elapsed)}`\n\n"
                f"{location_text}"
            )
            await status_msg.edit_text(success_text, reply_markup=keyboard)
        else:
            print(f"❌ Upload failed: {msg}")
            await status_msg.edit_text(f"❌ **Upload Failed:** `{msg}`")


# ---- Start/Help fallback for non-media text ---- #
@app.on_message(
    filters.private
    & filters.text
    & ~filters.command(["start", "help", "status", "storage", "setfolder", "recent"])
)
async def text_fallback(client: Client, message: Message):
    user_id = message.from_user.id
    print(f"💬 Text received from {message.from_user.first_name} (ID: {user_id}): {message.text}")

    if not is_authorized(user_id):
        await message.reply_text(
            f"⛔ **Access Denied:** Your User ID `{user_id}` is not authorized.\n"
            f"Set `OWNER_ID = {user_id}` in Colab."
        )
        return

    await message.reply_text(
        "📎 **Send me any media** (video, document, audio, photo) to upload to Mega.nz!\n\n"
        "Type `/help` for all commands.",
    )


# ---- Main Entry Point (Standard Pyrogram app.run() like GDrive bot) ---- #
if __name__ == "__main__":
    print("🚀 Mega.nz Telegram Bot is starting...")
    print(f"📂 Target Mega folder: {Config.MEGA_FOLDER}")
    if Config.OWNER_ID:
        print(f"🔒 Restricted to user ID: {Config.OWNER_ID}")
    else:
        print("⚠️ No OWNER_ID set — bot is open to all users!")

    # Verify MEGAcmd status
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
