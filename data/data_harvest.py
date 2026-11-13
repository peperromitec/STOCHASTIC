"""Ejecutar desde la raíz: python -m data.data_harvest --url URL_CSV."""

import argparse
from dataclasses import dataclass
import logging
from pathlib import Path

from dotenv import load_dotenv
import requests
from sqlalchemy.engine import Engine

from .database import check_schema, create_db_engine
from .links_ecobici import ecobici_links
from .normalization import normalize_csv
from .request import archive_csv, content_sha256, csv_file_name, download_csv
from .sql_writer import files_with_content, registered_file, sql_write_df
from .validation import validate_data

logger = logging.getLogger(__name__)


@dataclass
class HarvestSummary:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    quality_issues: int = 0


def process_file(engine, http, url, archive_dir, strict_quality=False):
    """Variables locales por archivo: un fallo jamás reutiliza otro DataFrame."""
    file_name = csv_file_name(url)
    if registered_file(engine, file_name) is not None:
        logger.info("Omitido: archivo=%s URL=%s ya registrado", file_name, url)
        return "skipped", False
    content = download_csv(http, url)
    original = archive_csv(content, file_name, archive_dir)
    sha256 = content_sha256(content)
    related = files_with_content(engine, sha256)
    if related:
        logger.warning(
            "Omitido: archivo=%s URL=%s bytes idénticos (SHA-256) a %s; original=%s",
            file_name, url, related, original,
        )
        return "skipped", False
    normalized = normalize_csv(content, file_name)
    for notice in normalized.notices:
        logger.warning("archivo=%s URL=%s: %s; original=%s", file_name, url, notice, original)
    issues = validate_data(normalized.frame)
    for issue in issues:
        logger.warning(
            "Calidad: archivo=%s URL=%s columna=%s cantidad=%s filas CSV=%s: %s",
            file_name, url, issue.column, issue.count, issue.csv_rows, issue.message,
        )
    if strict_quality and issues:
        raise ValueError(f"{file_name}: validaciones de calidad no superadas; no se importó")
    result = sql_write_df(engine, normalized.frame, file_name, sha256)
    if result.status == "identical_content":
        logger.warning(
            "Omitido: archivo=%s URL=%s bytes idénticos (SHA-256) a %s; original=%s",
            file_name, url, result.related_files, original,
        )
        return "skipped", bool(issues)
    if result.status == "already_registered":
        logger.info("Omitido: archivo=%s URL=%s registrado durante la ejecución", file_name, url)
        return "skipped", bool(issues)
    if result.same_row_count_files:
        logger.warning(
            "archivo=%s URL=%s mismo row_count que %s: solo sospecha, no prueba duplicación",
            file_name, url, result.same_row_count_files,
        )
    # sql_write_df vuelve únicamente tras completar el commit.
    logger.info(
        "Importado: archivo=%s URL=%s id=%s filas=%s; calidad=%s; original=%s",
        file_name, url, result.register_id, result.row_count,
        "con observaciones" if issues else "validaciones superadas", original,
    )
    return "imported", bool(issues)


def run_import(
    engine: Engine, http: requests.Session, urls, archive_dir: Path,
    strict_quality: bool = False,
) -> HarvestSummary:
    summary = HarvestSummary()
    for url in urls:
        try:
            status, has_issues = process_file(engine, http, url, archive_dir, strict_quality)
        except Exception as error:
            # Única frontera que captura errores para continuar el lote.
            # Los helpers propagan; la transacción del archivo ya fue revertida.
            logger.error(
                "Falló: archivo=%s URL=%s causa=%s: %s",
                url.rsplit("/", 1)[-1], url, type(error).__name__, error,
            )
            summary.failed += 1
            continue
        setattr(summary, status, getattr(summary, status) + 1)
        summary.quality_issues += int(has_issues)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Importa CSV de Ecobici por archivo")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", action="append", help="URL de CSV; se puede repetir")
    source.add_argument("--discover", action="store_true", help="Importar los CSV del portal")
    parser.add_argument("--archive-dir", type=Path, default=Path("downloads/ecobici"))
    parser.add_argument("--strict-quality", action="store_true", help="No cargar si hay observaciones")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    engine = create_db_engine()
    try:
        check_schema(engine)
        with requests.Session() as http:
            urls = ecobici_links(http) if args.discover else args.url
            summary = run_import(engine, http, urls, args.archive_dir, args.strict_quality)
        logger.info(
            "Resultado: importados=%s omitidos=%s fallidos=%s archivos con observaciones=%s",
            summary.imported, summary.skipped, summary.failed, summary.quality_issues,
        )
        return int(summary.failed > 0)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
