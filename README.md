# Ne_prosroch_bot

Telegram mini app для учёта продуктов дома: следит за сроками годности,
напоминает о том, что скоро испортится, и подбирает рецепты, чтобы
использовать продукты вовремя.

## Состав

- **backend** — FastAPI (REST для mini app), aiogram-бот, APScheduler.
- **core** — расчёт срочности (`UrgencyCalculator`) и жадный подбор набора
  рецептов (`GreedyRecommender`).
- **frontend** — Vite + React + TypeScript, интерфейс mini app.
- **migrations** — Alembic.
- **tests** — тесты алгоритмов и эксперимент «жадный против точного перебора».

## Требования

- Python 3.11+
- PostgreSQL 15+
- Node.js 20+ (для фронтенда)

## Запуск БД

Если PostgreSQL установлена локально, `docker-compose.yml` не нужен —
достаточно указать в `.env` рабочие `DATABASE_URL` и `ALEMBIC_DATABASE_URL`.

Вариант в контейнере: параметры берутся из `.env` (переменные `POSTGRES_*`),
данные лежат в именованном томе `pgdata` и переживают перезапуск контейнера.

```bash
copy .env.example .env             # Windows; POSTGRES_* можно оставить как есть
docker compose up -d db            # поднять
docker compose ps                  # готовность: healthy в колонке STATUS
docker compose exec db pg_isready  # -U и -d берутся из окружения контейнера
docker compose stop db             # остановить, данные сохраняются
```

Удалить контейнер вместе с данными: `docker compose down -v`.

## Запуск

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

copy .env.example .env        # заполнить DATABASE_URL и BOT_TOKEN
alembic upgrade head
python -m backend.db.seed     # наполнение справочников

uvicorn backend.main:app --reload
python -m backend.bot.main    # бот отдельным процессом
```

Планировщик поднимается вместе с API, отдельного процесса под него нет.
Задач две, расписание у них разное:

- **напоминания** — ежечасно в начале часа. Время напоминания у каждого
  своё, из настроек (`user_settings.notify_time`, по умолчанию 09:00);
  задача берёт тех пользователей, у кого час совпал с текущим;
- **списание просроченного** — раз в сутки в `DAILY_CHECK_TIME`.

`DAILY_CHECK_TIME` относится **только к списанию** и на время напоминаний
не влияет. Часовой пояс общий для всех, из `TIMEZONE`: персонального
пояса в модели данных нет.

Бот работает через long polling, вебхук не разворачивается.

## Наполнение справочников

```bash
python -m backend.db.seed
```

Заполняет `product_statuses`, `categories`, `ingredients`, `recipes`
и `recipe_ingredients` данными из `backend/db/seed.py`. Запускается после
`alembic upgrade head`. Операция идемпотентна: записи добавляются
по естественному ключу, существующие пропускаются, повторный запуск ничего
не дублирует и не падает. В конце выводится, сколько записей создано
и сколько пропущено по каждой таблице.

Правки справочников вносятся в структуры в начале `backend/db/seed.py`;
согласованность (все ингредиенты рецептов есть в справочнике, состав
из 3–6 позиций, нет дублей) проверяется до обращения к БД.

## Фронтенд

```bash
cd frontend
copy .env.example .env        # VITE_API_URL, по умолчанию /api через прокси
npm install
npm run dev                   # http://localhost:5173
npm run build                 # проверка типов и сборка в dist/
```

В разработке vite проксирует `/api` на `http://localhost:8000`, поэтому
запросы идут с того же источника и CORS не мешает. SDK Telegram Web Apps
подключается скриптом в `index.html`, пакета npm для него нет.

Вне Telegram приложение открывается, но API отвечает 401: подписи
`initData` нет, а без неё доступа к данным быть не должно.

## Тесты

```bash
pytest
```

Эксперимент со сравнением алгоритмов:

```bash
pytest tests/test_experiment.py -s
```
