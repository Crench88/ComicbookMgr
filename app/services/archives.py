"""Comic archive helpers for the digital reader (CBZ via zipfile, CBR via rarfile)."""

from __future__ import annotations

import io
import re
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MIME_BY_EXT = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}

ZIP_EXTENSIONS = {'.cbz', '.zip'}
RAR_EXTENSIONS = {'.cbr', '.rar'}
SUPPORTED_EXTENSIONS = ZIP_EXTENSIONS | RAR_EXTENSIONS

# Archive-bomb / abuse guardrails for uploads and page listing.
MAX_PAGES = 800
MAX_COMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB archive
MAX_UNCOMPRESSED_BYTES = 800 * 1024 * 1024  # 800 MB total pages
MAX_SINGLE_PAGE_BYTES = 40 * 1024 * 1024  # 40 MB per page


class ArchiveError(ValueError):
    """Raised when a digital comic archive is invalid or unsafe."""


class ArchiveToolMissingError(ArchiveError):
    """Raised when CBR support is requested but no RAR tool is available."""


_NAT_SPLIT = re.compile(r'(\d+)')


def natural_sort_key(value: str):
    parts = _NAT_SPLIT.split(value.lower().replace('\\', '/'))
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return key


def is_image_member(name: str) -> bool:
    path = Path(name.replace('\\', '/'))
    if any(part.startswith('.') for part in path.parts):
        return False
    if path.name.startswith('.'):
        return False
    return path.suffix.lower() in IMAGE_EXTENSIONS


def mime_for_member(name: str) -> str:
    ext = Path(name.replace('\\', '/')).suffix.lower()
    return MIME_BY_EXT.get(ext, 'application/octet-stream')


def format_for_filename(filename: str) -> str:
    """Return 'cbz' or 'cbr' for a filename, or raise for anything else."""
    ext = Path((filename or '').replace('\\', '/')).suffix.lower()
    if ext in ZIP_EXTENSIONS:
        return 'cbz'
    if ext in RAR_EXTENSIONS:
        return 'cbr'
    raise ArchiveError('Only .cbz and .cbr files are supported.')


def rar_support_error() -> str | None:
    """Return a human-readable reason when CBR cannot be read, else None."""
    try:
        import rarfile
    except ImportError:
        return 'CBR support needs the rarfile package (pip install rarfile).'
    try:
        rarfile.tool_setup()
    except Exception:
        return (
            'CBR support needs an unrar or bsdtar executable on PATH. '
            'Install one, then restart the app.'
        )
    return None


def rar_support_available() -> bool:
    return rar_support_error() is None


def _require_rarfile():
    problem = rar_support_error()
    if problem:
        raise ArchiveToolMissingError(problem)
    import rarfile

    return rarfile


class _ArchiveHandle:
    """Uniform view over a ZIP or RAR archive."""

    def __init__(self, entries, read, verify):
        self.entries = entries  # list[(name, uncompressed_size)]
        self.read = read
        self.verify = verify


@contextmanager
def open_archive(source, archive_format: str):
    """Yield an _ArchiveHandle for a path or file-like source."""
    if archive_format == 'cbz':
        try:
            with zipfile.ZipFile(source, 'r') as zf:
                entries = [
                    (info.filename, info.file_size)
                    for info in zf.infolist()
                    if not info.is_dir()
                ]
                yield _ArchiveHandle(entries, zf.read, zf.testzip)
        except zipfile.BadZipFile as exc:
            raise ArchiveError('File is not a valid CBZ/ZIP archive.') from exc
    elif archive_format == 'cbr':
        rarfile = _require_rarfile()
        try:
            with rarfile.RarFile(source) as rf:
                entries = []
                for info in rf.infolist():
                    is_dir = getattr(info, 'is_dir', None)
                    if callable(is_dir) and is_dir():
                        continue
                    entries.append((info.filename, info.file_size or 0))
                yield _ArchiveHandle(entries, rf.read, rf.testrar)
        except ArchiveError:
            raise
        except rarfile.NeedFirstVolume as exc:
            raise ArchiveError('This CBR is part of a multi-volume set.') from exc
        except rarfile.PasswordRequired as exc:
            raise ArchiveError('Password-protected CBR files are not supported.') from exc
        except rarfile.Error as exc:
            raise ArchiveError('File is not a valid CBR/RAR archive.') from exc
    else:
        raise ArchiveError(f'Unsupported archive format: {archive_format!r}')


def _collect_pages(handle: _ArchiveHandle, label: str) -> list[str]:
    members = []
    total_uncompressed = 0
    for name, size in handle.entries:
        if not is_image_member(name):
            continue
        if size > MAX_SINGLE_PAGE_BYTES:
            raise ArchiveError('A page inside the archive is too large.')
        total_uncompressed += size
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ArchiveError('Archive expands to an unsafe size.')
        members.append(name)

    if not members:
        raise ArchiveError(f'No readable page images found in the {label}.')
    if len(members) > MAX_PAGES:
        raise ArchiveError(f'{label} has too many pages (max {MAX_PAGES}).')

    members.sort(key=natural_sort_key)
    return members


def list_pages(archive_path: Path, archive_format: str | None = None) -> list[str]:
    """Return naturally sorted page member names inside an archive."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise ArchiveError('Digital comic file is missing.')

    size = archive_path.stat().st_size
    if size <= 0:
        raise ArchiveError('Digital comic file is empty.')
    if size > MAX_COMPRESSED_BYTES:
        raise ArchiveError('Digital comic file is too large.')

    archive_format = archive_format or format_for_filename(archive_path.name)
    with open_archive(archive_path, archive_format) as handle:
        return _collect_pages(handle, archive_format.upper())


def read_page(
    archive_path: Path,
    page_number: int,
    archive_format: str | None = None,
    members: list[str] | None = None,
) -> tuple[bytes, str]:
    """Return (bytes, mime) for a 1-based page number."""
    archive_path = Path(archive_path)
    archive_format = archive_format or format_for_filename(archive_path.name)
    if members is None:
        members = list_pages(archive_path, archive_format)
    if page_number < 1 or page_number > len(members):
        raise ArchiveError('Page number is out of range.')

    member = members[page_number - 1]
    with open_archive(archive_path, archive_format) as handle:
        data = handle.read(member)
    if not data:
        raise ArchiveError('Page image is empty.')
    if len(data) > MAX_SINGLE_PAGE_BYTES:
        raise ArchiveError('Page image is too large.')
    return data, mime_for_member(member)


def validate_upload(file_storage) -> tuple[bytes, int, str, str]:
    """
    Validate an uploaded archive and return
    (raw_bytes, page_count, original_filename, archive_format).
    """
    filename = (getattr(file_storage, 'filename', None) or '').strip()
    if not filename:
        raise ArchiveError('Choose a CBZ or CBR file to upload.')

    archive_format = format_for_filename(filename)

    raw = file_storage.read()
    if not raw:
        raise ArchiveError('Uploaded file is empty.')
    if len(raw) > MAX_COMPRESSED_BYTES:
        raise ArchiveError('Digital comic file is too large.')

    if archive_format == 'cbz':
        with open_archive(io.BytesIO(raw), 'cbz') as handle:
            if handle.verify() is not None:
                raise ArchiveError('Digital comic archive is corrupt.')
            page_count = len(_collect_pages(handle, 'CBZ'))
    else:
        # rarfile needs a real file for reliable tool-based extraction.
        problem = rar_support_error()
        if problem:
            raise ArchiveToolMissingError(problem)
        with tempfile.NamedTemporaryFile(suffix='.cbr', delete=False) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        try:
            with open_archive(tmp_path, 'cbr') as handle:
                page_count = len(_collect_pages(handle, 'CBR'))
        finally:
            tmp_path.unlink(missing_ok=True)

    return raw, page_count, Path(filename).name, archive_format


# Backwards-compatible CBZ-only helpers.


def list_cbz_pages(archive_path: Path) -> list[str]:
    return list_pages(archive_path, 'cbz')


def read_cbz_page(archive_path: Path, page_number: int) -> tuple[bytes, str]:
    return read_page(archive_path, page_number, 'cbz')


def validate_cbz_upload(file_storage) -> tuple[bytes, int, str]:
    raw, page_count, filename, _ = validate_upload(file_storage)
    return raw, page_count, filename
