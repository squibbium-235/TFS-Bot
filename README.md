# Sanctuary Servo

Discord bot for server verification, forms, welcome messages, custom commands, and an optional operator Web UI.

## Features included

- Slash commands and a small set of prefix commands
- Verification applications, staff review, and questioning threads
- Forms, DM templates, and welcome messages after approval
- Custom prefix commands
- Permission levels for commands and for the Web UI
- Encrypted SQLCipher database and encrypted `.tfsbackup` files
- Optional Web UI for owners (and a read-only overview for viewers)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`. `DISCORD_TOKEN` and `TFSBOT_DATABASE_KEY` are required. `.env.example` lists the rest.

## Run

From the repository root (the directory that contains `src`):

```bash
python -m src.main
```

The Web UI is optional. It starts only when `WEBUI_ENABLED` is true. By default it listens on `127.0.0.1:5050`.

## Discord Developer Portal

Enable these privileged intents. Prefix commands need message content, and verification needs the member list:

- Message Content Intent
- Server Members Intent

Invite scopes:

- `bot`
- `applications.commands`

## Server owner manual

Operators should read [docs/Sanctuary-Servo-Server-Owner-Manual.docx](docs/Sanctuary-Servo-Server-Owner-Manual.docx). It covers setup, permissions, the Web UI, verification, forms, custom commands, welcome messages, backups, and troubleshooting.

To regenerate that file (not required to run the bot):

```bash
pip install python-docx
python docs/build_server_owner_manual.py
```
