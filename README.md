⚡Telegram to Mega.nz Uploader (Colab Edition)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-v2.0%2B-orange?logo=telegram)](https://github.com/pyrogram/pyrogram)
[![Mega](https://img.shields.io/badge/MEGA-Official%20MEGAcmd-red?logo=mega)](https://mega.io/cmd)
[![Colab](https://img.shields.io/badge/Google%20Colab-Ready-yellow?logo=googlecolab)](https://colab.research.google.com/)

A fast, automated Telegram bot designed to upload videos, documents, music, and photos from **Telegram directly to Mega.nz** using **Google Colab** as a free cloud server.

Powered by the official **MEGAcmd** C++ engine — completely bypassing the modern MEGA API 402 Proof-of-Work bot-detection challenges.

---

## ✨ Features

- 🚀 **Fast Cloud Uploads**: Leverages Google Colab's high-speed datacenter connection (up to 100 MB/s).
- 💾 **20 GB Free Cloud Storage**: Upload directly to your personal Mega.nz account.
- ⚡ **Official MEGAcmd Engine**: Rock-solid stability without rate limits, session drops, or `402` blocks.
- 📊 **Live Progress Bar**: Displays real-time download speed, percentage, transferred bytes, and ETA.
- 🛡️ **Duplicate Protection**: Automatically detects existing files on Mega and appends timestamps to prevent overwrites.
- 📁 **Custom Folder Support**: Choose where files are saved with `/setfolder`.
- 🔒 **Owner Security Lock**: Restricts bot access strictly to your Telegram User ID (`OWNER_ID`).
- 🧹 **Auto-Cleanup**: Automatically purges temporary files from Colab disk after upload to prevent running out of storage.
- 📋 **Upload Tracker**: Tracks your upload stats and last 10 uploads using SQLite (zero setup).

---

## 🤖 Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Start the bot & display interactive menu |
| `/help` | Complete usage guide and instructions |
| `/setfolder <name>` | Change destination subfolder on Mega (e.g., `/setfolder Lectures`) |
| `/setfolder default` | Reset destination folder back to `/TelegramUploads` |
| `/status` | View your personal upload statistics (files & bytes) |
| `/storage` | Check real-time Mega.nz account storage (used, free, total) |
| `/recent` | View your last 10 uploaded files with details |
| **Send Media** | Send or forward any video, audio, or document to upload |

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
