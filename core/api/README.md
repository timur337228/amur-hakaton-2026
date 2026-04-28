# Budget Analytics

Проект разделён на два слоя:

- `FastAPI` в `core/api` отвечает только за API.
- `Django` в `core/web` отвечает за сайт и статические файлы.

## Установка Python-зависимостей

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Запуск через Docker Compose

```powershell
docker compose up --build
```

После запуска будут доступны сервисы:

- `FastAPI API`: `http://localhost:8000`
- `Django-сайт`: `http://localhost:8001`
- `PostgreSQL`: `localhost:5432`

Если ты используешь локальный импорт через интерфейс, у тебя есть два варианта:

- положить данные в `./project_file`
- или указать внешний путь через `PROJECT_FILE_HOST_PATH` в `.env`

Внутри контейнера этот каталог монтируется в `/app/project_file`, поэтому в форме можно по-прежнему указывать путь `project_file`.

## Локальный запуск FastAPI

```powershell
.\.venv\Scripts\python.exe -m uvicorn core.api.app.main:app --reload --port 8000
```

При старте API теперь применяет миграции `Alembic` вместо `Base.metadata.create_all(...)`.
При необходимости их можно прогнать отдельно:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Локальный запуск Django

```powershell
.\.venv\Scripts\python.exe manage.py runserver 8001
```

По умолчанию `Django` обращается к API по адресу `http://localhost:8000`.
Если нужно, этот адрес можно переопределить через `BUDGET_API_BASE_URL`.

Пример:

```powershell
$env:BUDGET_API_BASE_URL="http://localhost:8000"
.\.venv\Scripts\python.exe manage.py runserver 8001
```

## Первый импорт

Импорт локальной папки кейса:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/imports/local-path `
  -ContentType "application/json" `
  -Body '{"path":"project_file"}'
```

Загрузка архива:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/imports/archive `
  -F "file=@dataset.zip"
```

Для загрузки папки через фронтенд отправляются `multipart files` и соответствующие им `relative_paths`.

Все варианты импорта теперь запускаются в фоне:

- `POST` возвращает `batch_id` и статус `queued`
- затем фронтенд или внешний клиент опрашивает `GET /api/v1/imports/{batch_id}`
- после статуса `completed` или `completed_with_errors` можно запрашивать превью, статистику и аналитику

## Основные эндпоинты

- `POST /api/v1/imports/archive` — принимает `.zip`, `.rar`, `.7z`
- `POST /api/v1/imports/files` — принимает несколько файлов вместе с относительными путями
- `POST /api/v1/imports/local-path` — импорт из локального пути на сервере для dev/admin-сценариев
- `GET /api/v1/imports/{batch_id}` — сводка по импорту
- `GET /api/v1/imports/{batch_id}/files` — список импортированных файлов
- `GET /api/v1/imports/{batch_id}/errors` — ошибки импорта
- `POST /api/v1/analytics/transcribe-audio` — speech-to-text для голосового запроса

## Голосовой ввод

В интерфейсе можно загрузить аудиофайл или записать голосовой запрос с микрофона.

Поддерживаются два режима:

- `Whisper API` через `302.ai`
- локальный `faster-whisper`

Выбор задаётся в `config.yaml` через секцию `whisper` или через env-переменные:

- `WHISPER_PROVIDER=api|local`
- `WHISPER_API_MODEL=whisper-v3-turbo`
- `WHISPER_LOCAL_MODEL=large-v3-turbo`
- `WHISPER_POSTPROCESS_WITH_LLM=true|false`

Если включён `WHISPER_POSTPROCESS_WITH_LLM`, после распознавания система дополнительно уточняет текст через LLM по контексту текущего набора данных. Это помогает поправлять типичные ASR-ошибки вроде `Благовещ` -> `Благовещенск`, но добавляет задержку. По умолчанию этап выключен.

## CORS

Для локальной разработки API разрешает запросы с адресов:

- `http://localhost:8000`
- `http://127.0.0.1:8000`
- `http://localhost:8001`
- `http://127.0.0.1:8001`

Этот список можно переопределить через `CORS_ALLOW_ORIGINS`.

## Переменные окружения

Используй `.env.example` как шаблон для локального запуска и Docker.

Для Docker-импорта локальной папки особенно важна переменная:

- `PROJECT_FILE_HOST_PATH` — путь на хосте к папке с данными, например `/media/timur/UBUNTU 24_0/хакатон/project/project_file`

Если LLM недоступен, аналитика и экспорт продолжают работать по ручным фильтрам, а интерфейс показывает предупреждение.

Схема БД управляется через `Alembic`.
