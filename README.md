# ⚡ Telegram to Mega.nz Uploader (Batch & Queue Edition)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-v2.0%2B-orange?logo=telegram)](https://github.com/pyrogram/pyrogram)
[![Mega](https://img.shields.io/badge/MEGA-Official%20MEGAcmd-red?logo=mega)](https://mega.io/cmd)
[![Colab](https://img.shields.io/badge/Google%20Colab-Ready-yellow?logo=googlecolab)](https://colab.research.google.com/)

A fast, automated Telegram bot designed to upload videos, documents, music, and photos from **Telegram directly to Mega.nz** using **Google Colab** as a free cloud server.

Powered by an asynchronous **Sequential Queue** and the official **MEGAcmd** C++ engine — completely eliminating rate limits, disk overflow, and bot errors when transferring multiple large files.

---

## ✨ Features

- 📥 **Batch Forwarding**: Select and forward 10, 20, or 50+ videos at once — the bot queues and uploads them **one by one automatically**.
- 🔗 **Message Link Range (`/batch`)**: Batch download by link range (e.g. `https://t.me/c/.../96-100`).
- ⚡ **Sequential Queue Worker**: Downloads and uploads one file at a time so Colab disk space never fills up and uploads never collide.
- 💾 **20 GB Free Cloud Storage**: Uploads directly to your personal Mega.nz account.
- 🚀 **Datacenter Speeds**: Leverages Google Colab's high-speed connection (40–100 MB/s).
- 🛡️ **Duplicate Protection**: Automatically detects existing files on Mega and appends timestamps to prevent overwrites.
- 📊 **Live Progress Bar**: Displays real-time download speed, percentage, transferred bytes, and ETA.
- 📁 **Custom Folder Support**: Choose where files are saved with `/setfolder`.
- 🔒 **Owner Security Lock**: Restricts bot access strictly to your Telegram User ID (`OWNER_ID`).
- 🧹 **Instant Disk Cleanup**: Automatically purges temporary files from Colab disk immediately after each upload.
- 📋 **Upload Tracker**: Tracks your upload stats and last 10 uploads using SQLite (zero setup).

---

## 🤖 Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Start the bot & display interactive menu |
| `/help` | Complete usage guide and instructions |
| `/batch <url>-<range>` | Fetch and queue messages from a link range (e.g. `https://t.me/c/3930712197/96-100`) |
| `/queue` | Check currently processing file and total items waiting in queue |
| `/clearqueue` | Cancel and clear all pending uploads from the queue |
| `/setfolder <name>` | Change destination subfolder on Mega (e.g., `/setfolder Lectures`) |
| `/setfolder default` | Reset destination folder back to `/TelegramUploads` |
| `/status` | View your personal upload statistics (files & bytes) |
| `/storage` | Check real-time Mega.nz account storage (used, free, total) |
| `/recent` | View your last 10 uploaded files with details |
| **Forward Media** | Select single or multiple files in any chat and forward here |

---

## 🚀 1-Click Google Colab Setup

Open a new notebook on [Google Colab](https://colab.research.google.com/) and create 3 code cells:

### 📌 Cell 1: Environment Setup
```python
# 1. Step out to /content first
%cd /content

# 2. Install official MEGAcmd (Ubuntu 22.04 LTS)
!apt-get update -qq
!wget -q https://mega.nz/linux/repo/xUbuntu_22.04/amd64/megacmd-xUbuntu_22.04_amd64.deb -O /tmp/megacmd.deb
!apt-get install -y -qq /tmp/megacmd.deb

# 3. Clone repository & install dependencies
!rm -rf /content/tg-to-mega
!git clone https://github.com/debnathrahul635-hue/tg-to-mega.git /content/tg-to-mega
%cd /content/tg-to-mega
!pip install -q -r requirements.txt
```

---

### 📌 Cell 2: Configure Credentials
```python
#@title ⚙️ Mega.nz Telegram Bot Credentials { run: "auto" }
import os

API_ID = 0 #@param {type:"integer"}
API_HASH = "" #@param {type:"string"}
BOT_TOKEN = "" #@param {type:"string"}
OWNER_ID = 0 #@param {type:"integer"}
MEGA_EMAIL = "" #@param {type:"string"}
MEGA_PASSWORD = "" #@param {type:"string"}
MEGA_FOLDER = "/TelegramUploads" #@param {type:"string"}

os.environ["API_ID"] = str(API_ID)
os.environ["API_HASH"] = str(API_HASH)
os.environ["BOT_TOKEN"] = str(BOT_TOKEN)
os.environ["OWNER_ID"] = str(OWNER_ID)
os.environ["MEGA_EMAIL"] = str(MEGA_EMAIL)
os.environ["MEGA_PASSWORD"] = str(MEGA_PASSWORD)
os.environ["MEGA_FOLDER"] = str(MEGA_FOLDER)

# Authenticate with official MEGA engine
!mega-login "{MEGA_EMAIL}" "{MEGA_PASSWORD}"
!mega-whoami

print("✅ Configuration and MEGAcmd login verified!")
```

---

### 📌 Cell 3: Start the Bot
```python
!python bot.py
```

---

## 💡 How Batch Uploading Works

### Method A: Multi-Select & Forward (Easiest)
1. Open any channel or chat on Telegram.
2. Select 5, 10, 20, or more videos/documents.
3. Forward them all at once to this bot.
4. The bot will assign each one a position (`#1, #2, #3...`) and process them sequentially in the background.

### Method B: Link Range
1. Copy the link of the first message: `https://t.me/c/3930712197/96`
2. Add `-<end_id>` to specify the range: `https://t.me/c/3930712197/96-100`
3. Send to bot: `/batch https://t.me/c/3930712197/96-100`
*(Note: If the channel is private and the bot is not a member, use Method A instead).*

---

## 🔑 Where to Get Credentials?

1. **Telegram `API_ID` & `API_HASH`**:
   - Log in at [my.telegram.org](https://my.telegram.org).
   - Go to **API development tools** and create an app.
2. **Telegram `BOT_TOKEN`**:
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Use `/newbot` and copy the HTTP API token.
3. **Telegram `OWNER_ID`**:
   - Message [@userinfobot](https://t.me/userinfobot) on Telegram to get your numeric User ID.
4. **Mega Account**:
   - Sign up for a free account with 20 GB at [mega.nz](https://mega.nz).

---

## 📂 Project Architecture

```text
tg-to-mega/
├── bot.py                # Main bot entry point, Queue worker & message handlers
├── config.py             # Environment variable loader & defaults
├── database.py           # SQLite database for stats & upload history
├── downloader.py         # Pyrogram media downloader with live progress callback
├── mega_cli.py           # Official MEGAcmd wrapper (login, upload, deduplication)
├── progress.py           # Progress bar calculation, speed, and ETA formatting
├── requirements.txt      # Python package dependencies
├── .gitignore            # Git ignore rules
└── README.md             # Documentation
```

---

## 🔒 Security & Privacy

- All credentials (`BOT_TOKEN`, `MEGA_PASSWORD`, etc.) are passed via environment variables.
- By setting `OWNER_ID`, only your Telegram account can interact with the bot. Any unauthorized users are automatically denied.
- Temporary files on Colab are immediately removed upon upload completion.

---

## ⚖️ License

Distributed under the [MIT License](LICENSE).
