# Budget Analytics API

FastAPI service for importing case datasets from `project_file`, uploaded folders, or archives.

## Install Python Dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn core.api.app.main:app --reload --port 8000
```

## First Import

Import the local case folder:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/imports/local-path `
  -ContentType "application/json" `
  -Body '{"path":"project_file"}'
```

Upload an archive:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/imports/archive `
  -F "file=@dataset.zip"
```

Upload a folder from the frontend by sending multipart `files` plus matching `relative_paths`.

## Main Endpoints

- `POST /api/v1/imports/archive` - accepts `.zip`, `.rar`, `.7z`.
- `POST /api/v1/imports/files` - accepts multiple files with relative paths.
- `POST /api/v1/imports/local-path` - dev/admin import from a server-local path.
- `GET /api/v1/imports/{batch_id}` - import summary.
- `GET /api/v1/imports/{batch_id}/files` - imported files.
- `GET /api/v1/imports/{batch_id}/errors` - import errors.

Tables are created automatically at startup for the MVP. Replace this with Alembic migrations later.
