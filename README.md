# Remnabot

Telegram bot for the [Remnawave](https://remna.st) VPN panel — built with **aiogram 3**, **PostgreSQL**, **Redis**, and **Docker**.

## Quick Start (Windows local dev)

### 1. Install `uv`
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone & setup environment
```powershell
cd f:\Work\VPN\Remnabot
uv sync
Copy-Item .env.example .env
# Edit .env with your bot token, Remnawave URL/token, DB and Redis credentials
notepad .env
```

### 3. Start PostgreSQL & Redis with Docker
```powershell
docker compose up -d postgres redis
```

### 4. Run the bot
```powershell
uv run python -m bot.main
```

## Deploy on Ubuntu Server (VPS)

If you are deploying on a fresh Ubuntu Linux server, follow these steps:

### 1. Install Docker and Docker Compose
Run the following commands to install Docker:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

### 2. Transfer the project to your Server
You can either push your code to a private GitHub repository and `git clone` it on the server, or use an SFTP client (like WinSCP or FileZilla) to copy the `Remnabot` folder to your server (e.g., into `/root/Remnabot`).

```bash
git clone https://github.com/nzrmohammad/Remnahub.git
```

### 3. Setup the Environment File
Navigate to the project folder on your server:
```bash
cd /root/Remnabot
cp .env.example .env
nano .env
```
Fill in your `BOT_TOKEN`, `REMNAWAVE_API_URL`, `REMNAWAVE_API_TOKEN`, and `ADMIN_GROUP_ID`. Press `Ctrl+O`, `Enter`, and `Ctrl+X` to save and exit.

### 4. Build and Start the Containers
This command will download PostgreSQL and Redis, build the bot image, and start them all in the background:
```bash
docker compose up --build -d
```

### 5. Managing the Bot
- **View logs:** `docker compose logs -f bot`
- **Stop bot:** `docker compose down`
- **Restart after code changes:** `docker compose up --build -d`


---

## Environment Variables

### Telegram
| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot API token | Yes |
| `ADMIN_IDS` | Admin Telegram IDs (comma-separated) | Yes |
| `ADMIN_GROUP_ID` | Group ID for admin notifications | Yes |
| `ADMIN_TOPIC_ID` | Topic ID for new service requests | Yes |
| `PAYMENT_RECEIPTS_TOPIC_ID` | Topic ID for payment receipts | Yes |

### Remnawave Panel
| Variable | Description | Required |
|----------|-------------|----------|
| `REMNAWAVE_API_URL` | Remnawave panel URL | Yes |
| `REMNAWAVE_API_TOKEN` | Remnawave API token | Yes |

### Database
| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | Yes |

### Redis
| Variable | Description | Required |
|----------|-------------|----------|
| `REDIS_URL` | Redis connection URL (default: `redis://redis:6379/0`) | No |

### Tutorial Links
Connection guide links for each OS and app:
| Variable | Description |
|----------|-------------|
| `TUTORIAL_ANDROID_HAPP` | Android - HAPP app guide |
| `TUTORIAL_ANDROID_HIDDIFY` | Android - Hiddify guide |
| `TUTORIAL_ANDROID_V2RAYNG` | Android - V2rayNG guide |
| `TUTORIAL_IOS_HAPP` | iOS - HAPP app guide |
| `TUTORIAL_IOS_HIDDIFY` | iOS - Hiddify guide |
| `TUTORIAL_IOS_V2RAYNG` | iOS - V2rayNG guide |
| `TUTORIAL_WINDOWS_HAPP` | Windows - HAPP app guide |
| `TUTORIAL_WINDOWS_HIDDIFY` | Windows - Hiddify guide |
| `TUTORIAL_WINDOWS_V2RAYNG` | Windows - V2rayNG guide |

### Other Settings
| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `PAYMENT_CARD_NUMBER` | Payment card number displayed to users | - |
| `PAYMENT_CARD_HOLDER` | Card holder name | - |


---

## New Features

### Connection Guide (Tutorial)
Users can select their operating system and preferred app to receive tailored connection instructions:
- **OS Selection:** Android, iOS, Windows
- **App Selection:** HAPP (recommended), Hiddify, V2rayNG
- Links are configured via environment variables

### Warning Settings
Users can enable/disable notifications for:
- **Expiry Warning:** Notifies when subscription is about to expire
- **Volume Warning:** Notifies when data limit is running low

These settings are stored in the `users` table:
- `expiry_warning_enabled` (boolean, default: true)
- `volume_warning_enabled` (boolean, default: true)


---

## Project Structure

```
remnabot/
├── bot/
│   ├── main.py              # Entry point
│   ├── config.py            # Settings (pydantic-settings)
│   ├── core/
│   │   ├── dispatcher.py    # Bot + Dispatcher factory
│   │   ├── i18n.py          # Translation helper t(lang, key)
│   │   └── middlewares/
│   │       └── db.py        # DB session per update
│   ├── db/
│   │   ├── base.py          # SQLAlchemy Base
│   │   ├── engine.py        # Async engine + session factory
│   │   └── models/
│   │       └── user.py      # User model
│   ├── remnawave/
│   │   └── client.py        # Async Remnawave API client
│   ├── handlers/
│   │   ├── start.py         # /start command
│   │   ├── auth.py          # Language select, login, new service
│   │   └── menu.py          # All main menu sections
│   ├── keyboards/
│   │   └── inline.py        # All inline keyboards
│   ├── states/
│   │   └── fsm.py           # FSM state groups
│   └── locales/
│       ├── en.json          # English strings
│       └── fa.json          # Persian strings
├── migrations/              # Alembic migrations
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── pyproject.toml
└── .env.example
```
