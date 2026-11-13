"""Las observaciones de calidad no corrigen ni eliminan viajes."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class QualityIssue:
    column: str
    count: int
    csv_rows: list[int]
    message: str


def validate_data(frame: pd.DataFrame) -> list[QualityIssue]:
    issues = []

    def report(column, mask, message):
        if mask.any():
            issues.append(QualityIssue(
                column, int(mask.sum()),
                [int(index) + 2 for index in frame.index[mask][:5]], message,
            ))

    for column in frame:
        report(column, frame[column].isna(), "valor faltante")
    report("end_time", frame.end_time < frame.begin_time, "arribo anterior al retiro")
    report("age", frame.age < 0, "edad negativa")
    return issues
