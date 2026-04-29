# Budget Analytics

Система для загрузки бюджетных данных, поиска показателей на естественном языке и построения сводной аналитики по объектам, организациям, кодам и периодам.

Проект сделан в виде двух независимых слоёв:

- `FastAPI` отвечает только за API, импорт данных, аналитику, экспорт и speech-to-text
- `Django` отвечает за пользовательский сайт
## Демо

Приложение доступно по ссылке:
https://budget-analytics28.ru/

## Что умеет проект

- автоматически подхватывать стартовый набор данных из `project_file`
- импортировать архивы и папки с CSV
- строить аналитику по текстовому запросу и ручным фильтрам
- показывать итоги, таблицы и графики
- экспортировать сводный результат в `Excel`
- принимать голосовой запрос через `Whisper`
- работать в режиме витрины `deploy: true`, когда пользователь не может загружать свои файлы
## Стек

- Backend API: FastAPI
- Веб-приложение: Django
- База данных: PostgreSQLPRO
- ORM и миграции: SQLAlchemy + Alembic
- Контейнеризация: Docker, Docker Compose
- Reverse proxy и HTTPS: Caddy
- Работа с речью: Whisper (API и локальный faster-whisper)
- LLM: YandexGPT (дообучение через SFT) или API 302.ai Deepseek-v4 fast
- Frontend: Django templates (SSR)
## Архитектура

- `core/api` — API на `FastAPI`
- `core/web` — сайт на `Django`
- `training/llm_sft` — датасет для дообучения модели
- `notebooks` — ноутбуки для экспериментов и обучения
- `scripts` — утилиты генерации датасета и запуска обучения
- `project_file` — стартовый набор CSV
- `storage` — импортированные данные и служебные файлы

## Быстрый старт

### 1. Установка зависимостей

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка окружения

Создай `.env` на основе `.env.example`.

Минимально обычно нужны:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `LLM_API_KEY`
- `DJANGO_SECRET_KEY`

### 3. Запуск через Docker

Для локальной разработки:

```bash
docker compose up --build
```

После запуска будут доступны:

- API: `http://localhost:8000`
- сайт: `http://localhost:8001`

## Локальный запуск без Docker

### API

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn core.api.app.main:app --reload --port 8000
```

### Сайт

```bash
.venv/bin/python manage.py runserver 8001
```

По умолчанию сайт обращается к API по `http://localhost:8000`.

## Импорт данных

Есть три основных сценария:

- автоимпорт стартового набора из `project_file`
- загрузка архива
- загрузка папки/набора файлов

После запуска импорта создаётся `batch`, который обрабатывается в фоне. Затем фронтенд опрашивает его статус и показывает результат.

Полезные эндпоинты:

- `POST /api/v1/imports/default`
- `POST /api/v1/imports/archive`
- `POST /api/v1/imports/files`
- `GET /api/v1/imports/{batch_id}`

## Аналитика

Основной сценарий:

1. данные импортированы
2. пользователь вводит текстовый запрос или заполняет фильтры
3. API интерпретирует запрос
4. строится сводка, таблица, графики и Excel

Примеры запросов:

- `Покажи лимиты по Благовещенску по месяцам`
- `Покажи кассовые выплаты по 0502`
- `Покажи сумму контрактов по источнику gz`

Для этих трёх демо-запросов в интерфейсе используются заранее подготовленные ответы, чтобы результат открывался быстрее и стабильнее.

## Голосовой ввод

Поддерживаются два режима:

- `Whisper API` через `302.ai`
- локальный `faster-whisper`

Настройка идёт через `config.yaml`:

- `whisper.provider: api | local`
- `whisper.api_model`
- `whisper.local_model`
- `whisper.language`
- `whisper.postprocess_with_llm`

Сейчас дополнительная постобработка распознанного текста через LLM по умолчанию выключена, чтобы не замедлять систему.

## Режим деплоя

В `config.yaml` есть флаг:

```yaml
deploy: true
```

Если он включён:

- пользователь не может загружать свои архивы и папки
- сайт работает как витрина на уже подключённом наборе данных
- drag-and-drop в интерфейсе отключён
- API-ручки прямой загрузки блокируются

## Продакшен-запуск

Для боевого запуска используется:

- [docker-compose.prod.yml](./docker-compose.prod.yml)
- [Caddyfile](./Caddyfile)

Запуск:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Что поднимается:

- `PostgreSQL`
- `FastAPI`
- `Django`
- `Caddy` как reverse proxy и TLS-терминатор

`Caddy` автоматически выпускает HTTPS-сертификаты, если домен уже смотрит на сервер.

## База данных

Схема БД управляется через `Alembic`.

Применить миграции вручную:

```bash
.venv/bin/python -m alembic upgrade head
```

## Excel-экспорт

Экспорт формирует не сырую выгрузку CSV, а аналитический отчёт.

В файле есть листы:

- `Параметры`
- `Сводка по объектам`
- `Итоги по объектам`
- `Динамика`
- `Детализация`

Это соответствует задаче: пользователь выбирает объект, показатели и период, а на выходе получает сводный файл с лимитами, обязательствами, кассовыми выплатами, соглашениями, контрактами и динамикой.

## Дообучение модели

В проекте есть артефакты для SFT-задачи:

`text query -> JSON filters`

Основные файлы:

- [training/llm_sft/budget_query_sft_train.jsonl](./training/llm_sft/budget_query_sft_train.jsonl)
- [training/llm_sft/budget_query_sft_val.jsonl](./training/llm_sft/budget_query_sft_val.jsonl)
- [training/llm_sft/dataset_loader.py](./training/llm_sft/dataset_loader.py)
- [scripts/generate_budget_sft_assets.py](./scripts/generate_budget_sft_assets.py)
- [scripts/train_yandexgpt5_lite_t4.py](./scripts/train_yandexgpt5_lite_t4.py)

Скрипт `train_yandexgpt5_lite_t4.py` подготовлен под запуск в `Google Colab` с `T4`:

- умеет монтировать `Google Drive`
- умеет брать `HF_TOKEN` из `Colab Secrets`
- может подхватывать датасет из проекта или попросить загрузить `jsonl`

## Тесты

Запуск основных тестов:

```bash
.venv/bin/python -m unittest tests.test_site
.venv/bin/python -m unittest tests.test_analytics
.venv/bin/python -m unittest tests.test_import_jobs
```

Проверка Django:

```bash
.venv/bin/python manage.py check
```

## Основные файлы конфигурации

- [config.yaml](./config.yaml) — общие настройки проекта
- [.env.example](./.env.example) — шаблон переменных окружения
- [requirements.txt](./requirements.txt) — Python-зависимости
- [core/api/README.md](./core/api/README.md) — техническое описание API-слоя

## Примечания

- Для продакшена не коммить реальные ключи и пароли.
- Для HTTPS домен должен уже смотреть на IP сервера.
- Для локального импорта в Docker путь с данными должен быть смонтирован в контейнер.
