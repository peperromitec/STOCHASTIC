"""Registro y viajes se escriben con la misma conexión y transacción."""

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .normalization import DATA_COLUMNS
from .schemas.data_model import Data
from .schemas.file_register_model import FileRegister


@dataclass
class ImportResult:
    status: str
    register_id: int | None = None
    row_count: int = 0
    related_files: tuple[str, ...] = ()
    same_row_count_files: tuple[str, ...] = ()


def registered_file(engine: Engine, file_name: str) -> int | None:
    with engine.connect() as connection:
        return connection.scalar(
            select(FileRegister.id).where(FileRegister.file_name == file_name)
        )


def files_with_content(engine: Engine, sha256: str) -> tuple[str, ...]:
    with engine.connect() as connection:
        return tuple(connection.scalars(
            select(FileRegister.file_name)
            .where(FileRegister.content_sha256 == sha256)
            .order_by(FileRegister.file_name)
        ))


def sql_write_df(
    engine: Engine, frame: pd.DataFrame, file_name: str, sha256: str,
) -> ImportResult:
    if set(frame.columns) != set(DATA_COLUMNS) or frame.columns.duplicated().any():
        raise ValueError(f"{file_name}: se esperaba un DataFrame ya normalizado")
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise ValueError(f"{file_name}: SHA-256 inválido")
    try:
        with engine.begin() as connection:
            existing = connection.scalar(
                select(FileRegister.id).where(FileRegister.file_name == file_name)
            )
            if existing is not None:
                return ImportResult("already_registered", register_id=existing)
            related = tuple(connection.scalars(
                select(FileRegister.file_name)
                .where(FileRegister.content_sha256 == sha256)
                .order_by(FileRegister.file_name)
            ))
            if related:
                return ImportResult("identical_content", related_files=related)
            similar_counts = tuple(connection.scalars(
                select(FileRegister.file_name)
                .where(FileRegister.row_count == len(frame))
                .order_by(FileRegister.file_name)
            ))
            # Exigir la tabla completa antes de to_sql; nunca crear tablas aquí.
            connection.execute(select(Data.__table__).limit(0))
            register_id = connection.scalar(
                insert(FileRegister).values(
                    file_name=file_name,
                    process_date=datetime.now(timezone.utc).replace(tzinfo=None),
                    content_sha256=sha256,
                ).returning(FileRegister.id)
            )
            trips = frame.assign(file_register_id=register_id)
            trips.to_sql(
                Data.__tablename__, con=connection, if_exists="append", index=False,
                chunksize=10_000,
            )
            actual_count = connection.scalar(
                select(func.count()).select_from(Data)
                .where(Data.file_register_id == register_id)
            )
            if actual_count != len(frame):
                raise RuntimeError(
                    f"{file_name}: se esperaban {len(frame)} viajes, se insertaron {actual_count}"
                )
            connection.execute(
                update(FileRegister).where(FileRegister.id == register_id)
                .values(row_count=actual_count)
            )
            result = ImportResult(
                "imported", register_id, actual_count,
                same_row_count_files=similar_counts,
            )
        # Salir de engine.begin() hace el commit; cualquier fallo se propaga.
        return result
    except IntegrityError:
        # Resuelve la carrera entre la consulta previa y el UNIQUE de file_name.
        # engine.begin() ya revirtió también cualquier viaje insertado.
        existing = registered_file(engine, file_name)
        if existing is not None:
            return ImportResult("already_registered", register_id=existing)
        raise
