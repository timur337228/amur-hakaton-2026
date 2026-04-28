from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path


class ArchiveError(RuntimeError):
    pass


ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}


def is_supported_archive(filename: str) -> bool:
    return Path(filename).suffix.lower() in ARCHIVE_EXTENSIONS


def extract_archive(archive_path: Path, destination: Path) -> None:
    extension = archive_path.suffix.lower()
    destination.mkdir(parents=True, exist_ok=True)

    if extension == ".zip":
        _extract_zip(archive_path, destination)
        return

    if extension == ".7z":
        if _extract_with_py7zr(archive_path, destination):
            return
        _extract_with_7z_binary(archive_path, destination)
        return

    if extension == ".rar":
        if _extract_with_rarfile(archive_path, destination):
            return
        _extract_with_7z_binary(archive_path, destination)
        return

    raise ArchiveError(f"Unsupported archive extension: {extension}")


def _extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target_path = (destination / member.filename).resolve()
            if not _is_relative_to(target_path, destination.resolve()):
                raise ArchiveError(f"Unsafe archive path: {member.filename}")
        archive.extractall(destination)


def _extract_with_py7zr(archive_path: Path, destination: Path) -> bool:
    try:
        import py7zr  # type: ignore
    except Exception:
        return False

    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        archive.extractall(path=destination)
    return True


def _extract_with_rarfile(archive_path: Path, destination: Path) -> bool:
    try:
        import rarfile  # type: ignore
    except Exception:
        return False

    with rarfile.RarFile(archive_path) as archive:
        archive.extractall(path=destination)
    return True


def _extract_with_7z_binary(archive_path: Path, destination: Path) -> None:
    binary = _find_7z()
    if not binary:
        raise ArchiveError(
            "Cannot extract archive. Install py7zr/rarfile or 7-Zip and make 7z.exe available."
        )

    result = subprocess.run(
        [str(binary), "x", "-y", f"-o{destination}", str(archive_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ArchiveError(result.stderr.strip() or result.stdout.strip() or "7-Zip extraction failed")


def _find_7z() -> Path | None:
    found = shutil.which("7z")
    if found:
        return Path(found)

    for candidate in (
        Path("C:/Program Files/7-Zip/7z.exe"),
        Path("C:/Program Files (x86)/7-Zip/7z.exe"),
    ):
        if candidate.exists():
            return candidate
    return None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
