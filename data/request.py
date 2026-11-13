"""Descarga de bytes y conservación del original, sin transformar datos."""

import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import requests


def csv_file_name(url: str) -> str:
    name = PurePosixPath(unquote(urlsplit(url).path)).name
    if not name.lower().endswith(".csv") or name in (".csv", "..csv"):
        raise ValueError(f"La URL no identifica un CSV: {url}")
    return name


def download_csv(session: requests.Session, url: str) -> bytes:
    with session.get(url, timeout=(10, 60)) as response:
        response.raise_for_status()
        return response.content


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def archive_csv(content: bytes, file_name: str, archive_dir: Path) -> Path:
    """No sobrescribe versiones distintas del mismo nombre."""
    if Path(file_name).name != file_name:
        raise ValueError(f"Nombre de archivo inseguro: {file_name!r}")
    target = Path(archive_dir) / content_sha256(content) / file_name
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as output:
            output.write(content)
    except FileExistsError:
        if target.read_bytes() != content:
            raise ValueError(f"El original guardado no coincide: {target}")
    return target
