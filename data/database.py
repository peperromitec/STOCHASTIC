"""Configuración compartida; la importación nunca crea ni migra tablas."""

import os

from sqlalchemy import Text, URL, create_engine, inspect
from sqlalchemy.engine import Engine

from .schemas.data_model import Data
from .schemas.file_register_model import FileRegister


def database_url(environ=None) -> URL:
    env = os.environ if environ is None else environ
    missing = [key for key in ("DB_USER", "DB_PASSWORD", "DB_NAME") if not env.get(key)]
    if missing:
        raise ValueError(f"Faltan variables de entorno: {', '.join(missing)}")
    return URL.create(
        "postgresql+psycopg",
        username=env["DB_USER"],
        password=env["DB_PASSWORD"],
        host=env.get("DB_HOST", "localhost"),
        port=int(env.get("DB_PORT", "5432")),
        database=env["DB_NAME"],
    )


def create_db_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


def check_schema(engine: Engine) -> None:
    """Fallar antes de descargar si falta aplicar la migración."""
    inspector = inspect(engine)
    for table in (Data.__table__, FileRegister.__table__):
        if not inspector.has_table(table.name):
            raise RuntimeError(f"Falta la tabla {table.name}; consulta README.md")
        columns = {col["name"]: col for col in inspector.get_columns(table.name)}
        missing = set(table.columns.keys()) - columns.keys()
        if missing:
            raise RuntimeError(
                f"{table.name}: faltan {sorted(missing)}; aplica la migración 001"
            )
        if table.name == "data":
            for name in ("bicycle_id", "begin_station", "end_station"):
                if not isinstance(columns[name]["type"], Text):
                    raise RuntimeError(f"data.{name} debe ser TEXT; aplica la migración 001")
    unique = inspector.get_unique_constraints("file_register")
    unique += [idx for idx in inspector.get_indexes("file_register") if idx["unique"]]
    if not any(item["column_names"] == ["file_name"] for item in unique):
        raise RuntimeError("file_register.file_name debe tener una restricción UNIQUE")
    if not any(
        fk["constrained_columns"] == ["file_register_id"]
        and fk["referred_table"] == "file_register"
        and fk["referred_columns"] == ["id"]
        for fk in inspector.get_foreign_keys("data")
    ):
        raise RuntimeError("Falta la FK data.file_register_id; aplica la migración 001")
