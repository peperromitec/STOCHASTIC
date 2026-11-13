"""Revisar faltantes en un CSV original sin convertir fechas ni tocar la BD."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from .normalization import ALIASES, CSV_COLUMNS, DATA_COLUMNS, NULL_MARKER_COLUMNS, header_key


def audit_csv(path: Path) -> dict:
    path = Path(path)
    with path.open("rb") as source:
        sha256 = hashlib.file_digest(source, "sha256").hexdigest()
    breakdown = Counter(totally_blank=0, only_blank_or_null_markers=0, partially_populated=0)
    missing_counts = Counter({column: 0 for column in DATA_COLUMNS})
    examples = {category: [] for category in breakdown}
    total = all_analysis_missing = raw_blank = raw_blank_or_null = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = next(reader, [])
        columns = [ALIASES.get(header_key(col), header_key(col)) for col in header]
        if len(set(columns)) != len(columns) or not set(CSV_COLUMNS).issubset(columns):
            raise ValueError(f"{path}: faltan columnas requeridas o hay colisiones de alias")
        for total, row in enumerate(reader, start=1):
            if not row:  # Una línea vacía también es un registro para esta auditoría.
                row = [""] * len(columns)
            if len(row) != len(columns):
                raise ValueError(f"{path}: línea {reader.line_num}: cantidad de campos incorrecta")
            values = [value.strip() for value in row]
            # Solo medir presencia: misma política de columnas que el importador.
            # Un valor inválido no vacío cuenta como poblado, nunca como faltante.
            missing = {
                col: not value or (col in NULL_MARKER_COLUMNS and value.casefold() == "null")
                for col, value in zip(columns, values)
            }
            analysis_missing = {
                col: missing[col] for col in DATA_COLUMNS if not col.endswith("_time")
            }
            for prefix in ("begin", "end"):
                analysis_missing[f"{prefix}_time"] = (
                    missing[f"{prefix}_date"] or missing[f"{prefix}_clock"]
                )
            missing_counts.update(col for col, absent in analysis_missing.items() if absent)
            all_analysis_missing += int(all(analysis_missing.values()))
            blank = not any(values)
            placeholder_only = all(value.casefold() in ("", "null") for value in values)
            raw_blank += int(blank)
            raw_blank_or_null += int(placeholder_only)
            if sum(analysis_missing.values()) < 2:
                continue
            category = (
                "totally_blank" if blank else
                "only_blank_or_null_markers" if placeholder_only else "partially_populated"
            )
            breakdown[category] += 1
            if len(examples[category]) < 5:
                examples[category].append({
                    "csv_record": total + 1,
                    "csv_end_line": reader.line_num,
                    "populated_source_columns": [
                        col for col, value in zip(columns, values)
                        if value.casefold() not in ("", "null")
                    ],
                })
    return {
        "file": str(path.resolve()), "content_sha256": sha256, "total_rows": total,
        "raw_blank_rows": raw_blank, "raw_blank_or_null_only_rows": raw_blank_or_null,
        "multiple_missing_definition": "Al menos dos de los siete campos de análisis faltantes",
        "multiple_missing_rows": sum(breakdown.values()),
        "multiple_missing_breakdown": dict(breakdown),
        "all_analysis_fields_missing_rows": all_analysis_missing,
        "missing_by_analysis_column": dict(missing_counts), "examples": examples,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(audit_csv(args.csv_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
