from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from ..db import SessionLocal
from .importer import ImportService


@dataclass(frozen=True)
class ImportJob:
    batch_id: str
    kind: str
    source_path: str


class ImportJobRunner:
    def __init__(self) -> None:
        self._queue: Queue[ImportJob | None] = Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._worker_loop, name="import-job-runner", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            thread = self._thread
            if not thread:
                return
            self._stop_event.set()
            self._queue.put(None)
            thread.join(timeout=timeout)
            self._thread = None

    def enqueue_archive(self, batch_id: str, archive_path: Path) -> None:
        self.enqueue(ImportJob(batch_id=batch_id, kind="archive", source_path=str(archive_path)))

    def enqueue_directory(self, batch_id: str, extracted_dir: Path) -> None:
        self.enqueue(ImportJob(batch_id=batch_id, kind="directory", source_path=str(extracted_dir)))

    def enqueue_local_path(self, batch_id: str, source_path: Path) -> None:
        self.enqueue(ImportJob(batch_id=batch_id, kind="local_path", source_path=str(source_path)))

    def enqueue(self, job: ImportJob) -> None:
        self.start()
        self._queue.put(job)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except Empty:
                continue

            if job is None:
                self._queue.task_done()
                break

            try:
                self._run_job(job)
            finally:
                self._queue.task_done()

    def _run_job(self, job: ImportJob) -> None:
        with SessionLocal() as db:
            service = ImportService(db)
            if job.kind == "archive":
                service.process_archive_batch(job.batch_id, Path(job.source_path))
                return
            if job.kind == "directory":
                service.process_saved_directory_batch(job.batch_id, Path(job.source_path))
                return
            if job.kind == "local_path":
                service.process_local_path_batch(job.batch_id, Path(job.source_path))
                return
            raise ValueError(f"Unsupported import job kind: {job.kind}")


_job_runner = ImportJobRunner()


def get_import_job_runner() -> ImportJobRunner:
    return _job_runner
