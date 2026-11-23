import time
import math
import asyncio
from pyrogram.errors import FloodWait

# Cache to throttle message editing (Telegram allows ~1 edit per 3 seconds per message)
_last_update_time = {}


def human_bytes(size: int) -> str:
    """Convert bytes to human-readable format."""
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = min(math.floor(math.log(size, 1024)), len(units) - 1)
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s} {units[i]}"


def time_formatter(seconds: float) -> str:
    """Convert seconds to human-readable time string."""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    res = ""
    if days > 0:
        res += f"{days}d "
    if hours > 0:
        res += f"{hours}h "
    if minutes > 0:
        res += f"{minutes}m "
    res += f"{seconds}s"
    return res


def create_progress_bar(current: int, total: int, length: int = 12) -> str:
    """Create a visual progress bar string."""
    if total <= 0:
        return "░" * length
    percentage = current / total
    filled = int(length * percentage)
    bar = "█" * filled + "░" * (length - filled)
    return bar


async def progress_callback(
    current: int,
    total: int,
    message,
    start_time: float,
    action_text: str = "📥 Downloading",
):
    """Callback for displaying upload/download progress in Telegram."""
    now = time.time()
    msg_id = message.id

    # Throttle edits to once every 3.5 seconds to avoid FloodWait
    last_time = _last_update_time.get(msg_id, 0)
    if (now - last_time) < 3.5 and current != total:
        return
    _last_update_time[msg_id] = now

    elapsed_time = now - start_time
    if elapsed_time <= 0:
        elapsed_time = 0.001

    speed = current / elapsed_time
    percentage = (current / total * 100) if total > 0 else 0
    bar = create_progress_bar(current, total, length=12)

    eta = (total - current) / speed if speed > 0 and total > 0 else 0
    eta_str = time_formatter(eta)
    speed_str = f"{human_bytes(int(speed))}/s"

    text = (
        f"**{action_text}**\n\n"
        f"`[{bar}]` **{percentage:.1f}%**\n\n"
        f"⚡ **Speed:** `{speed_str}`\n"
        f"📦 **Done:** `{human_bytes(current)}` / `{human_bytes(total)}`\n"
        f"⏳ **ETA:** `{eta_str}`\n"
        f"⏱️ **Elapsed:** `{time_formatter(elapsed_time)}`"
    )

    try:
        await message.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass
