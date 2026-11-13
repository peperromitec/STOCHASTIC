from pathlib import Path
import unittest

from data.audit_csv import audit_csv
from data.normalization import normalize_csv
from data.request import content_sha256
from data.validation import validate_data

SOURCE = Path(__file__).parent / "fixtures/sparse_rows.csv"


class CSVAuditTests(unittest.TestCase):
    def test_read_only_audit_distinguishes_blank_placeholder_and_partial_rows(self):
        original = SOURCE.read_bytes()
        report = audit_csv(SOURCE)
        self.assertEqual(SOURCE.read_bytes(), original)
        self.assertEqual(report["content_sha256"], content_sha256(original))
        self.assertEqual(report["total_rows"], 5)
        self.assertEqual(report["multiple_missing_rows"], 5)
        self.assertEqual(report["multiple_missing_breakdown"], {
            "totally_blank": 2, "only_blank_or_null_markers": 1, "partially_populated": 2,
        })
        self.assertEqual(report["raw_blank_rows"], 2)
        self.assertEqual(report["raw_blank_or_null_only_rows"], 3)
        self.assertEqual(report["all_analysis_fields_missing_rows"], 3)
        self.assertEqual(
            report["examples"]["partially_populated"][1]["populated_source_columns"],
            ["begin_clock"],
        )

    def test_sparse_rows_are_preserved_and_reported_by_normalizer(self):
        frame = normalize_csv(SOURCE.read_bytes(), SOURCE.name).frame
        self.assertEqual(len(frame), 5)
        # La última fila tiene una hora en el original, pero le falta la fecha.
        self.assertTrue(frame.loc[4].isna().all())
        self.assertEqual(int(frame.isna().all(axis=1).sum()), 3)
        self.assertEqual(frame.loc[2, "bicycle_id"], "NULL")
        issues = {issue.column: issue.count for issue in validate_data(frame)}
        self.assertEqual(issues["begin_time"], 5)
        self.assertEqual(issues["end_time"], 5)


if __name__ == "__main__":
    unittest.main()
