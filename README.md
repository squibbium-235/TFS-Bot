# TFSBot
## Features included

- `discord.py`
- Slash commands
- Text/prefix commands
- One command per file
- Shared embed helper
- Reusable Discord modal/form builder
- Basic `/ping`, `!ping`, `/info`, `!info`
- Basic `/setupverify` and `!setupverify` scaffold with a Verify button and modal

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your bot token.

## Run

From the repository root (the directory that contains `src`):

```bash
python -m src.main
```

The Web UI is optional. It starts only when `WEBUI_ENABLED` is true.

## Discord Developer Portal

Enable these intents for text commands and verification work:

- Message Content Intent
- Server Members Intent, later when roles/verification are added properly

Invite scopes:

- `bot`
- `applications.commands`
