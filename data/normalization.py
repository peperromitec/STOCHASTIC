"""Normalización estricta: nunca inferir día/mes ni perder códigos desconocidos."""

import csv
from dataclasses import dataclass
import io
import re

import pandas as pd


# BikeID tiene otra numeración: deliberadamente no es alias de Bici.
ALIASES = {
    "genero_usuario": "gender",
    "edad_usuario": "age",
    "bici": "bicycle_id",
    "ce_retiro": "begin_station",
    "ciclo_estacion_retiro": "begin_station",
    "ce_arribo": "end_station",
    "ciclo_estacionarribo": "end_station",
    "ciclo_estacion_arribo": "end_station",
    "fecha_retiro": "begin_date",
    "hora_retiro": "begin_clock",
    "fecha_arribo": "end_date",
    "hora_arribo": "end_clock",
}
CSV_COLUMNS = (
    "gender", "age", "bicycle_id", "begin_station", "begin_date", "begin_clock",
    "end_station", "end_date", "end_clock",
)
DATA_COLUMNS = (
    "gender", "age", "bicycle_id", "begin_station", "end_station",
    "begin_time", "end_time",
)
NULL_MARKER_COLUMNS = (
    "gender", "age", "begin_date", "begin_clock", "end_date", "end_clock",
)


@dataclass
class NormalizedCSV:
    frame: pd.DataFrame
    notices: list[str]


def header_key(value: str) -> str:
    value = value.replace("\ufeff", "").strip().casefold()
    return re.sub(r"_+", "_", re.sub(r"\s+", "_", value))


def normalize_missing_values(values: pd.Series, column: str) -> pd.Series:
    """Blancos en cualquier campo; NULL solo en las columnas documentadas."""
    missing = values.str.fullmatch(r"\s*", na=False)
    if column in NULL_MARKER_COLUMNS:
        missing |= values.str.strip().str.casefold().eq("null").fillna(False)
    return values.mask(missing, pd.NA)


def _bad_values(file_name, column, values, reason):
    examples = values.astype("string").dropna().drop_duplicates().head(5).tolist()
    return ValueError(
        f"{file_name}: columna {column}: {reason}; ejemplos={examples}"
    )


def _parse_component(values, file_name, column, formats):
    values = values.str.strip()
    result = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    present = values.notna()
    recognized = ~present
    for pattern, fmt in formats:
        mask = present & values.str.fullmatch(pattern, na=False)
        recognized |= mask
        if not mask.any():
            continue
        try:
            result.loc[mask] = pd.to_datetime(values.loc[mask], format=fmt, errors="raise")
        except (ValueError, OverflowError) as error:
            # Solo en la ruta de error, localizar ejemplos inválidos con precisión.
            bad = []
            for value in values.loc[mask].drop_duplicates():
                try:
                    pd.to_datetime(value, format=fmt, errors="raise").as_unit("ns")
                except (ValueError, OverflowError):
                    bad.append(value)
                if len(bad) == 5:
                    break
            raise _bad_values(
                file_name, column, pd.Series(bad or values.loc[mask].head(5)),
                f"fecha/hora inválida ({fmt})",
            ) from error
    if not recognized.all():
        raise _bad_values(
            file_name, column, values.loc[~recognized], "formato no admitido"
        )
    return result


def _timestamp(frame, prefix, file_name):
    dates = _parse_component(frame[f"{prefix}_date"], file_name, f"{prefix}_date", (
        (r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y"),
        (r"\d{2}/\d{2}/\d{2}", "%d/%m/%y"),
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    ))
    # Limitar rangos ANTES del parser: pandas puede normalizar segundos=60.
    clock_pattern = r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    clocks = _parse_component(frame[f"{prefix}_clock"], file_name, f"{prefix}_clock", (
        (clock_pattern, "%H:%M:%S"),
        (clock_pattern + r"\.[0-9]{1,6}", "%H:%M:%S.%f"),
    ))
    # Ambas partes se validan por separado, incluso si falta la otra.
    return dates + (clocks - pd.Timestamp("1900-01-01"))


def normalize_csv(content: bytes, file_name: str) -> NormalizedCSV:
    text = content.decode("utf-8-sig", errors="strict")
    reader = csv.reader(io.StringIO(text), strict=True)
    try:
        original = next(reader)
    except StopIteration as error:
        raise ValueError(f"{file_name}: CSV vacío") from error
    columns = [ALIASES.get(header_key(col), header_key(col)) for col in original]
    notices = []

    # Solo el archivo confirmado y la estructura conocida de nueve campos.
    # Inspeccionar antes de que pandas convierta el encabezado duplicado en .1.
    broken_june = list(CSV_COLUMNS[:-1]) + ["begin_clock"]
    mangled_june = list(CSV_COLUMNS[:-1]) + ["hora_retiro.1"]
    if file_name == "2021-06.csv" and columns in (broken_june, mangled_june):
        columns[-1] = "end_clock"
        notices.append("Corrección confirmada 2021-06: último Hora_Retiro → Hora_Arribo")

    collisions = {
        col: [raw for raw, canonical in zip(original, columns) if canonical == col]
        for col in columns if columns.count(col) > 1
    }
    if collisions:
        raise ValueError(f"{file_name}: colisiones de encabezados/alias: {collisions}")
    missing = set(CSV_COLUMNS) - set(columns)
    if missing:
        raise ValueError(
            f"{file_name}: faltan columnas requeridas {sorted(missing)}; "
            f"encabezados={original}"
        )
    # Evitar que pandas interprete un campo extra como índice y pierda datos.
    for row in reader:
        if row and len(row) != len(original):
            raise ValueError(
                f"{file_name}: línea CSV {reader.line_num}: "
                f"{len(row)} campos, se esperaban {len(original)}"
            )
    frame = pd.read_csv(
        io.StringIO(text), dtype="string", keep_default_na=False, na_values=[""],
        skip_blank_lines=False, on_bad_lines="error",
    )
    frame.columns = columns
    if frame.empty:
        raise ValueError(f"{file_name}: el CSV no contiene viajes")
    # Faltantes centralizados antes de convertir tipos o validar. El marcador
    # NULL se reconoce en gender, age y las partes de fecha/hora; los códigos
    # de identificadores y estaciones (incluidos 'NULL' o 'NA') se conservan.
    for col in frame:
        frame[col] = normalize_missing_values(frame[col], col)
    extras = [col for col in columns if col not in CSV_COLUMNS]
    if "bikeid" in extras:
        notices.append("BikeID excluido del análisis; se conserva Bici y el CSV original")
    others = [col for col in extras if col != "bikeid"]
    if others:
        notices.append(f"Columnas excluidas del análisis, conservadas en el original: {others}")

    age = frame["age"].str.strip()
    invalid = age.notna() & ~age.str.fullmatch(r"[+-]?\d+", na=False)
    if invalid.any():
        raise _bad_values(file_name, "age", age.loc[invalid], "se esperaba un entero")
    try:
        frame["age"] = age.astype("Int64")
    except (ValueError, OverflowError) as error:
        raise _bad_values(file_name, "age", age, "entero fuera de rango") from error
    outside = (frame["age"] < -(2**31)) | (frame["age"] > 2**31 - 1)
    if outside.any():
        raise _bad_values(file_name, "age", age.loc[outside], "fuera de INTEGER PostgreSQL")
    long_gender = frame["gender"].str.len() > 1
    if long_gender.any():
        raise _bad_values(
            file_name, "gender", frame.loc[long_gender, "gender"], "excede VARCHAR(1)"
        )
    frame["begin_time"] = _timestamp(frame, "begin", file_name)
    frame["end_time"] = _timestamp(frame, "end", file_name)
    return NormalizedCSV(frame.loc[:, list(DATA_COLUMNS)], notices)
