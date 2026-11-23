import os


class Config:
    # Telegram API Credentials (Get from https://my.telegram.org)
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "")

    # Telegram Bot Token (Get from @BotFather)
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

    # Telegram User ID of the Owner (only this user can use the bot, set 0 to allow all)
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

    # Mega.nz Account Credentials
    MEGA_EMAIL = os.environ.get("MEGA_EMAIL", "")
    MEGA_PASSWORD = os.environ.get("MEGA_PASSWORD", "")

    # Mega.nz target folder path (e.g. "/TelegramUploads" or "/Root")
    # Files will be uploaded to this folder inside your Mega drive
    MEGA_FOLDER = os.environ.get("MEGA_FOLDER", "/TelegramUploads")

    # Local temporary download directory (fallback if streaming fails)
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/content/downloads" if os.path.exists("/content") else "./downloads")

    # SQLite database path (no external DB needed!)
    DB_PATH = os.environ.get("DB_PATH", "bot_data.db")
