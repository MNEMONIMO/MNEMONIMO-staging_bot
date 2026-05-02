# 🏠 Staging Bot — AI Interior Visualization Telegram Bot

Telegram-бот для AI-визуализации интерьера. Пользователь отправляет фото комнаты, отвечает
на вопросы и получает фотореалистичные варианты будущего дизайна.

---

## 🏗 Архитектура

```
app/
├── bot/
│   ├── handlers/        # Telegram update handlers
│   │   ├── start.py     # /start, /help, /pricing, /examples
│   │   ├── project.py   # Полный FSM-сценарий создания проекта
│   │   ├── payment.py   # Тарифы и Telegram Payments
│   │   ├── my_projects.py # /myprojects + действия с проектами
│   │   └── admin.py     # Все /admin-команды
│   ├── keyboards/       # InlineKeyboard и ReplyKeyboard
│   ├── middlewares/     # AuthMiddleware, RateLimitMiddleware
│   ├── states/          # FSM states (aiogram 3)
│   ├── messages.py      # Все текстовые константы
│   └── main.py          # Точка входа (polling / webhook)
│
├── core/
│   ├── config.py        # Pydantic Settings из .env
│   └── logging.py       # Loguru setup
│
├── db/
│   ├── models/          # SQLAlchemy 2 ORM models
│   ├── migrations/      # Alembic env.py
│   └── session.py       # AsyncEngine + AsyncSession
│
├── repositories/        # Data access layer
│   ├── user_repository.py
│   ├── project_repository.py
│   ├── payment_repository.py
│   ├── generation_job_repository.py
│   └── audit_log_repository.py
│
├── services/
│   ├── generation/      # AI pipeline orchestration
│   └── notification/    # Send results back to users
│
├── integrations/
│   ├── ai/client.py     # Replicate / Stability AI adapter
│   └── storage/s3.py    # S3-compatible file storage
│
├── workers/
│   ├── celery_app.py    # Celery app config
│   └── tasks/
│       └── generation.py # Celery task: run_generation_task
│
└── utils/
    └── watermark.py     # PIL watermark for free plan
```

---

## 🚀 Быстрый старт

### 1. Клонируй и настрой окружение

```bash
git clone <repo>
cd staging_bot
cp .env.example .env
# Заполни .env: BOT_TOKEN, DATABASE_URL, AI_API_KEY, S3_*, PAYMENT_TOKEN
```

### 2. Запусти через Docker Compose

```bash
docker-compose up -d
```

### 3. Примени миграции

```bash
docker-compose exec bot alembic upgrade head
```

### 4. Запусти бота

```bash
# Polling (dev)
python -m app.bot.main

# Webhook (production) — установи WEBHOOK_HOST в .env
python -c "import asyncio; from app.bot.main import run_webhook; asyncio.run(run_webhook())"
```

### 5. Запусти Celery worker

```bash
celery -A app.workers.celery_app worker --loglevel=info --concurrency=4
```

---

## ⚙️ Конфигурация (.env)

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram бота (@BotFather) |
| `ADMIN_IDS` | Telegram ID администраторов (через запятую) |
| `DATABASE_URL` | PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis DSN (`redis://localhost:6379/0`) |
| `AI_PROVIDER` | Провайдер генерации: `replicate` |
| `AI_API_KEY` | API-ключ провайдера |
| `AI_MODEL` | Версия модели на Replicate |
| `S3_*` | Параметры S3-совместимого хранилища |
| `PAYMENT_TOKEN` | Токен для Telegram Payments |
| `PRICE_ROOM` | Цена тарифа Room в копейках (49900 = 499₽) |

---

## 🤖 Команды бота

### Пользователь
| Команда | Описание |
|---|---|
| `/start` | Главное меню |
| `/new` | Создать новый проект |
| `/myprojects` | Мои проекты |
| `/pricing` | Тарифы |
| `/examples` | Примеры работ |
| `/help` | Помощь |

### Администратор
| Команда | Описание |
|---|---|
| `/admin` | Панель администратора |
| `/projects [status]` | Список проектов |
| `/project <id>` | Детали проекта |
| `/retry <id>` | Перезапустить генерацию |
| `/stats` | Статистика |
| `/broadcast` | Рассылка всем пользователям |

---

## 💳 Тарифы

| Тариф | Цена | Варианты | Shopping list | Водяной знак |
|---|---|---|---|---|
| Free | 0₽ | 1 preview | ❌ | ✅ |
| Room | 499₽ | 3 | Базовый | ❌ |
| Pro Room | 999₽ | 4 | Расширенный | ❌ |
| Flat | 1999₽ | 4 (несколько комнат) | ✅ | ❌ |
| Realtor Pack | 2999₽ | 4 + приоритет | ✅ | ❌ |

---

## 🔄 FSM-состояния проекта

```
idle → room_type → area → ceiling_height → style → budget
     → free_space → keep_items → remove_items → extra_notes
     → photos → confirmation → tariff_selection
     → [free: generate] / [paid: payment → queued]
     → analyzing → generating → postprocessing → done
```

---

## 🛠 Интеграция AI

Файл: `app/integrations/ai/client.py`

По умолчанию используется **Replicate** (SDXL). Для смены провайдера:
1. Реализуй метод `_call_<provider>()` в `AIGenerationClient`
2. Обнови `AI_PROVIDER` и `AI_MODEL` в `.env`

---

## 📊 База данных

Таблицы: `users`, `projects`, `project_images`, `payments`, `generation_jobs`, `audit_logs`

```bash
# Создать миграцию после изменений модели
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

## 📝 Лицензия

MIT
