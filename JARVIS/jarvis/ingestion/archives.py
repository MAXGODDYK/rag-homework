from __future__ import annotations

import shutil
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from .parsers import PARSERS, TEXT_EXTENSIONS, is_blocked_path, is_probably_text


class ArchiveSafetyError(RuntimeError):
    """Archive failed a deterministic safety check."""


ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".7z", ".rar")


def is_archive(path: Path) -> bool:
    lowered = path.name.lower()
    return any(lowered.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def _safe_relative(name: str) -> Path:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or ".." in pure.parts
        or any(":" in part for part in pure.parts)
    ):
        raise ArchiveSafetyError(f"Unsafe archive path: {name}")
    return Path(*pure.parts)


def _supported_member(path: Path) -> bool:
    if is_blocked_path(path) or is_archive(path):
        return False
    return (
        path.suffix.lower() in TEXT_EXTENSIONS
        or path.suffix.lower() in PARSERS
        or path.name.lower() in {"dockerfile", "makefile"}
    )


def _validate_totals(
    files: int,
    extracted_bytes: int,
    compressed_bytes: int,
    max_files: int,
    max_extracted_bytes: int,
) -> None:
    if files > max_files:
        raise ArchiveSafetyError(f"Archive exceeds {max_files} files")
    if extracted_bytes > max_extracted_bytes:
        raise ArchiveSafetyError("Archive exceeds the extracted-size quota")
    if compressed_bytes > 0 and extracted_bytes / compressed_bytes > 100:
        raise ArchiveSafetyError("Archive compression ratio exceeds 100:1")


def _copy_stream(source, target: Path, maximum: int) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with target.open("wb") as output:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > maximum:
                raise ArchiveSafetyError("Archive member exceeds remaining quota")
            output.write(block)
    return total


def _extract_zip(path: Path, destination: Path, max_files: int, max_bytes: int) -> list[Path]:
    extracted: list[Path] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        _validate_totals(len(infos), sum(info.file_size for info in infos), sum(info.compress_size for info in infos), max_files, max_bytes)
        for info in infos:
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArchiveSafetyError("Archive symlinks are forbidden")
            relative = _safe_relative(info.filename)
            if not _supported_member(relative):
                continue
            target = destination / relative
            with archive.open(info) as source:
                total += _copy_stream(source, target, max_bytes - total)
            extracted.append(target)
    return extracted


def _extract_tar(path: Path, destination: Path, max_files: int, max_bytes: int) -> list[Path]:
    extracted: list[Path] = []
    total = 0
    with tarfile.open(path, mode="r:*") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        if any(member.issym() or member.islnk() for member in archive.getmembers()):
            raise ArchiveSafetyError("Archive links are forbidden")
        _validate_totals(len(members), sum(member.size for member in members), path.stat().st_size, max_files, max_bytes)
        for member in members:
            relative = _safe_relative(member.name)
            if not _supported_member(relative):
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            target = destination / relative
            with source:
                total += _copy_stream(source, target, max_bytes - total)
            extracted.append(target)
    return extracted


def _extract_7z(path: Path, destination: Path, max_files: int, max_bytes: int) -> list[Path]:
    import py7zr

    with py7zr.SevenZipFile(path, mode="r") as archive:
        if archive.password_protected:
            raise ArchiveSafetyError("Encrypted archives are not supported")
        infos = archive.list()
        files = [info for info in infos if not info.is_directory]
        total = sum(int(info.uncompressed or 0) for info in files)
        _validate_totals(len(files), total, path.stat().st_size, max_files, max_bytes)
        targets: list[str] = []
        for info in files:
            relative = _safe_relative(info.filename)
            if _supported_member(relative):
                targets.append(info.filename)
        archive.extract(path=destination, targets=targets)
    extracted = [(destination / _safe_relative(name)).resolve() for name in targets]
    root = destination.resolve()
    if any(root not in file.parents for file in extracted):
        raise ArchiveSafetyError("7z extraction escaped its sandbox")
    if any(file.is_symlink() for file in extracted if file.exists()):
        raise ArchiveSafetyError("Extracted symlinks are forbidden")
    return [file for file in extracted if file.is_file()]


def _extract_rar(path: Path, destination: Path, max_files: int, max_bytes: int) -> list[Path]:
    import rarfile

    extracted: list[Path] = []
    total = 0
    try:
        archive = rarfile.RarFile(path)
    except rarfile.Error as error:
        raise ArchiveSafetyError("RAR could not be opened; a supported RAR backend is required") from error
    with archive:
        infos = [info for info in archive.infolist() if info.is_file()]
        if any(info.needs_password() for info in infos):
            raise ArchiveSafetyError("Encrypted archives are not supported")
        _validate_totals(len(infos), sum(info.file_size for info in infos), path.stat().st_size, max_files, max_bytes)
        for info in infos:
            relative = _safe_relative(info.filename)
            if not _supported_member(relative):
                continue
            target = destination / relative
            try:
                with archive.open(info) as source:
                    total += _copy_stream(source, target, max_bytes - total)
            except rarfile.Error as error:
                raise ArchiveSafetyError("RAR extraction failed safely") from error
            extracted.append(target)
    return extracted


def extract_archive(
    path: Path,
    destination: Path,
    *,
    max_files: int,
    max_extracted_bytes: int,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=False)
    lowered = path.name.lower()
    try:
        if lowered.endswith(".zip"):
            files = _extract_zip(path, destination, max_files, max_extracted_bytes)
        elif lowered.endswith((".tar", ".tar.gz", ".tgz")):
            files = _extract_tar(path, destination, max_files, max_extracted_bytes)
        elif lowered.endswith(".7z"):
            files = _extract_7z(path, destination, max_files, max_extracted_bytes)
        elif lowered.endswith(".rar"):
            files = _extract_rar(path, destination, max_files, max_extracted_bytes)
        else:
            raise ArchiveSafetyError("Unsupported archive format")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return [file for file in files if is_probably_text(file) or file.suffix.lower() in PARSERS]
