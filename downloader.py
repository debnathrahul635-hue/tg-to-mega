import os
import time
from typing import Optional
from config import Config
from progress import progress_callback

# Ensure download directory exists
os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)


async def download_telegram_file(client, message, status_msg) -> Optional[str]:
    """Downloads any Telegram media file to local disk with live progress tracking."""
    start_time = time.time()
    try:
        file_path = await client.download_media(
            message=message,
            file_name=os.path.join(Config.DOWNLOAD_DIR, ""),
            progress=progress_callback,
            progress_args=(status_msg, start_time, "📥 Downloading from Telegram"),
        )
        return file_path
    except Exception as e:
        await status_msg.edit_text(f"❌ **Download Failed:** `{str(e)}`")
        return None
