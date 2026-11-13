"""Pruebas pequeñas, sin red ni conexión a la base configurada en .env."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests
from sqlalchemy import create_engine, event, func, select

from data.data_harvest import run_import
from data.database import check_schema, database_url
from data.links_ecobici import ecobici_links
from data.normalization import normalize_csv
from data.request import content_sha256, csv_file_name, download_csv
from data.schemas.base import Base
from data.schemas.data_model import Data
from data.schemas.file_register_model import FileRegister
from data.sql_writer import sql_write_df
from data.validation import validate_data

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name="aliases.csv"):
    return (FIXTURES / name).read_bytes()


class NormalizationTests(unittest.TestCase):
    def test_aliases_bom_whitespace_and_bikeid(self):
        content = b'\xef\xbb\xbf' + fixture().replace(b"Fecha Arribo", b" Fecha   Arribo ")
        result = normalize_csv(content, "sample.csv")
        self.assertEqual(result.frame.loc[0, "gender"], "M")
        self.assertEqual(result.frame.loc[0, "bicycle_id"], "0007A")
        self.assertEqual(result.frame.loc[0, "begin_station"], "001")
        self.assertEqual(result.frame.loc[0, "end_station"], "271-272")
        self.assertNotIn("bikeid", result.frame.columns)
        self.assertTrue(any("BikeID excluido" in notice for notice in result.notices))

    def test_all_requested_station_and_user_aliases(self):
        for end in (b"CE_arribo", b"Ciclo_EstacionArribo", b"Ciclo_Estacion_Arribo"):
            for gender in (b"Genero_Usuario", b"Genero_usuario", b"GENERO_USUARIO"):
                with self.subTest(end=end, gender=gender):
                    content = fixture().replace(b"Ciclo_EstacionArribo", end)
                    content = content.replace(b"Genero_usuario", gender)
                    frame = normalize_csv(content, "sample.csv").frame
                    self.assertEqual(frame.loc[0, "end_station"], "271-272")

    def test_explicit_dates_and_fractional_seconds(self):
        frame = normalize_csv(fixture("dates.csv"), "dates.csv").frame
        self.assertEqual(frame.loc[0, "begin_time"], pd.Timestamp("2021-04-03 09:10:11.123456"))
        self.assertEqual(frame.loc[0, "end_time"], pd.Timestamp("2021-04-03 09:12:00.500000"))
        self.assertEqual(frame.loc[1, "begin_time"], pd.Timestamp("2021-12-11 23:59:59"))
        self.assertEqual(frame.loc[0, "bicycle_id"], "0001")
        self.assertEqual(frame.loc[1, "begin_station"], "271-272")

    def test_single_and_double_digit_hours_with_optional_fractions(self):
        frame = normalize_csv(fixture("clock_formats.csv"), "clocks.csv").frame
        self.assertEqual(frame["begin_time"].tolist(), [
            pd.Timestamp("2021-04-03 00:05:06"),
            pd.Timestamp("2021-04-03 00:05:06"),
            pd.Timestamp("2021-04-03 00:05:06.100000"),
            pd.Timestamp("2021-04-03 00:05:06.123456"),
        ])
        self.assertEqual(frame["end_time"].tolist(), [
            pd.Timestamp("2021-04-03 00:10:11"),
            pd.Timestamp("2021-04-03 00:10:11"),
            pd.Timestamp("2021-04-03 00:10:11.120000"),
            pd.Timestamp("2021-04-03 00:10:11.500000"),
        ])

    def test_valid_clock_range_boundaries(self):
        for value, expected in (
            (b"0:00:00", "00:00:00"),
            (b"00:00:00", "00:00:00"),
            (b"9:59:59", "09:59:59"),
            (b"19:59:59", "19:59:59"),
            (b"23:59:59.999999", "23:59:59.999999"),
        ):
            with self.subTest(value=value):
                content = fixture().replace(b"08:00:00", value).replace(b"08:15:00", value)
                frame = normalize_csv(content, "clocks.csv").frame
                timestamp = pd.Timestamp(f"2021-03-02 {expected}")
                self.assertEqual(frame.loc[0, "begin_time"], timestamp)
                self.assertEqual(frame.loc[0, "end_time"], timestamp)

    def test_invalid_clock_ranges_and_formats_are_rejected(self):
        for source, column in ((b"08:00:00", "begin_clock"), (b"08:15:00", "end_clock")):
            for value in (
                b"24:00:00", b"24:00:00.1", b"0:60:00", b"0:00:60",
                b"23:59:60", b"00:00:60", b"0:05:60.1", b"-1:00:00",
                b"001:05:06", b"0:5:06", b"0:05:6", b"NULLx", b"N/A",
            ):
                with self.subTest(column=column, value=value):
                    content = fixture().replace(source, value)
                    with self.assertRaisesRegex(ValueError, f"bad.csv.*{column}.*ejemplos"):
                        normalize_csv(content, "bad.csv")

    def test_temporal_missing_variants_after_alias_resolution(self):
        for marker in (b"NULL", b" null ", b" NuLl ", b"", b"   "):
            with self.subTest(marker=marker):
                content = fixture().replace(b"Fecha Arribo", b" Fecha   Arribo ")
                for source in (b"02/03/2021", b"2021-03-02", b"08:00:00", b"08:15:00"):
                    content = content.replace(source, marker)
                frame = normalize_csv(content, "missing.csv").frame
                self.assertTrue(pd.isna(frame.loc[0, "begin_time"]))
                self.assertTrue(pd.isna(frame.loc[0, "end_time"]))
                self.assertEqual(
                    {(issue.column, issue.message, issue.count) for issue in validate_data(frame)},
                    {("begin_time", "valor faltante", 1), ("end_time", "valor faltante", 1)},
                )

    def test_two_digit_year_dates_for_departure_and_arrival(self):
        frame = normalize_csv(fixture("date_formats.csv"), "202209.csv").frame
        self.assertEqual(frame["begin_time"].tolist(), [
            pd.Timestamp("2022-08-30 08:00:00"),
            pd.Timestamp("2022-08-31 23:59:59.123456"),
            pd.Timestamp("2022-09-01 09:00:00"),
            pd.Timestamp("2022-09-02 10:00:00"),
        ])
        self.assertEqual(frame["end_time"].tolist(), [
            pd.Timestamp("2022-08-30 08:15:00"),
            pd.Timestamp("2022-09-01 00:15:00"),
            pd.Timestamp("2022-09-01 09:15:00"),
            pd.Timestamp("2022-09-02 10:15:00"),
        ])

    def test_null_or_empty_date_and_clock_components_keep_timestamps_missing(self):
        frame = normalize_csv(fixture("date_null_markers.csv"), "missing.csv").frame
        self.assertTrue(frame["begin_time"].isna().all())
        self.assertTrue(frame["end_time"].isna().all())
        self.assertEqual(len(frame), 4)
        self.assertEqual(
            {(issue.column, issue.message, issue.count) for issue in validate_data(frame)},
            {("begin_time", "valor faltante", 4), ("end_time", "valor faltante", 4)},
        )

    def test_impossible_two_digit_year_dates_are_rejected(self):
        for source in (b"02/03/2021", b"2021-03-02"):
            column = "begin_date" if source == b"02/03/2021" else "end_date"
            for invalid in (b"31/02/22", b"29/02/21", b"31/04/22"):
                with self.subTest(column=column, invalid=invalid):
                    content = fixture().replace(source, invalid)
                    with self.assertRaisesRegex(ValueError, f"bad.csv.*{column}.*ejemplos"):
                        normalize_csv(content, "bad.csv")
        leap_day = fixture().replace(b"02/03/2021", b"29/02/20").replace(b"2021-03-02", b"29/02/20")
        frame = normalize_csv(leap_day, "leap.csv").frame
        self.assertEqual(frame.loc[0, "begin_time"], pd.Timestamp("2020-02-29 08:00:00"))
        self.assertEqual(frame.loc[0, "end_time"], pd.Timestamp("2020-02-29 08:15:00"))

    def test_invalid_temporal_value_not_hidden_by_null_partner(self):
        for column, source, invalid, partner in (
            ("begin_date", b"02/03/2021", b"31/02/22", b"08:00:00"),
            ("end_date", b"2021-03-02", b"31/04/22", b"08:15:00"),
            ("begin_clock", b"08:00:00", b"25:00:00", b"02/03/2021"),
            ("end_clock", b"08:15:00", b"99:00:00", b"2021-03-02"),
        ):
            with self.subTest(column=column):
                content = fixture().replace(source, invalid).replace(partner, b" NuLl ")
                with self.assertRaisesRegex(ValueError, f"bad.csv.*{column}.*ejemplos"):
                    normalize_csv(content, "bad.csv")

    def test_confirmed_june_header_and_pandas_suffix(self):
        for content in (
            fixture("2021-06.csv"),
            fixture("2021-06.csv").replace(b"Fecha_Arribo,Hora_Retiro", b"Fecha_Arribo,Hora_Retiro.1"),
        ):
            with self.subTest(content=content[:30]):
                result = normalize_csv(content, "2021-06.csv")
                self.assertEqual(result.frame.loc[0, "end_time"], pd.Timestamp("2021-06-04 08:10:00"))
                self.assertTrue(result.notices)

    def test_june_fix_is_not_generalized(self):
        with self.assertRaisesRegex(ValueError, "colisiones"):
            normalize_csv(fixture("2021-06.csv"), "2021-07.csv")
        # Ni siquiera junio se corrige si cambia la estructura conocida.
        changed = fixture("2021-06.csv").replace(b"Bici,", b"Bici,BikeID,")
        with self.assertRaisesRegex(ValueError, "colisiones"):
            normalize_csv(changed, "2021-06.csv")

    def test_alias_collision_and_missing_columns(self):
        collision = fixture().replace(b"BikeID", b"CE_arribo")
        with self.assertRaisesRegex(ValueError, "sample.csv.*colisiones.*end_station"):
            normalize_csv(collision, "sample.csv")
        with self.assertRaisesRegex(ValueError, "faltan columnas requeridas.*age"):
            normalize_csv(fixture().replace(b"Edad_Usuario", b"unknown"), "sample.csv")

    def test_invalid_nonempty_values_include_file_column_and_examples(self):
        for bad in (b"31/02/2021", b"2021/03/02", b"NULLx", b"N/A"):
            with self.subTest(bad=bad):
                content = fixture().replace(b"02/03/2021", bad)
                with self.assertRaisesRegex(ValueError, "bad.csv.*begin_date.*ejemplos"):
                    normalize_csv(content, "bad.csv")
        with self.assertRaisesRegex(ValueError, "begin_clock.*25:00:00"):
            normalize_csv(fixture().replace(b"08:00:00", b"25:00:00"), "bad.csv")
        with self.assertRaisesRegex(ValueError, "age.*desconocida"):
            normalize_csv(fixture().replace(b"M,25,", b"M,desconocida,"), "bad.csv")

    def test_missing_values_quality_and_unknown_identifiers_preserved(self):
        frame = normalize_csv(fixture("incomplete.csv"), "incomplete.csv").frame
        self.assertTrue(pd.isna(frame.loc[0, "age"]))
        self.assertEqual(frame.loc[0, "bicycle_id"], "NULL")
        self.assertTrue(pd.isna(frame.loc[1, "bicycle_id"]))
        self.assertTrue(pd.isna(frame.loc[1, "begin_time"]))
        self.assertEqual(len(frame), 2)
        before = frame.copy(deep=True)
        issues = validate_data(frame)
        self.assertTrue(any(issue.message == "arribo anterior al retiro" for issue in issues))
        self.assertTrue(any(issue.message == "valor faltante" for issue in issues))
        pd.testing.assert_frame_equal(frame, before)

    def test_null_markers_in_gender_and_age_are_missing_and_reported(self):
        frame = normalize_csv(fixture("null_markers.csv"), "null_markers.csv").frame
        self.assertTrue(frame["gender"].isna().all())
        self.assertTrue(frame["age"].isna().all())
        self.assertEqual(str(frame["age"].dtype), "Int64")
        self.assertEqual(frame.loc[0, "bicycle_id"], "0001")
        self.assertEqual(frame.loc[2, "bicycle_id"], "NULL")
        self.assertEqual(frame.loc[2, "begin_station"], "NULL")
        self.assertEqual(frame.loc[2, "end_station"], " NA ")
        issues = validate_data(frame)
        self.assertEqual(
            {(issue.column, issue.message, issue.count) for issue in issues},
            {("gender", "valor faltante", 3), ("age", "valor faltante", 3)},
        )

    def test_unknown_values_are_not_treated_as_null_markers(self):
        for gender, age, column in (
            (b"UNKNOWN", b"NULL", "gender"),
            (b"NULLx", b"25", "gender"),
            (b"NULL", b"desconocida", "age"),
            (b"M", b"N/A", "age"),
            (b"M", b"null 0", "age"),
        ):
            with self.subTest(gender=gender, age=age):
                content = fixture().replace(b"M,25,", gender + b"," + age + b",")
                with self.assertRaisesRegex(ValueError, f"bad.csv.*columna {column}.*ejemplos"):
                    normalize_csv(content, "bad.csv")

    def test_invalid_component_not_hidden_by_other_missing_component(self):
        content = fixture("incomplete.csv").replace(b",,,12:00:00,", b",,,25:00:00,")
        with self.assertRaisesRegex(ValueError, "begin_clock"):
            normalize_csv(content, "bad.csv")

    def test_malformed_csv_does_not_silently_shift_columns(self):
        with self.assertRaisesRegex(ValueError, "campos"):
            normalize_csv(fixture().replace(b",99999", b",99999,extra"), "bad.csv")


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def foreign_keys(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.temp = tempfile.TemporaryDirectory()
        self.archive = Path(self.temp.name)
        self.http = Mock(spec=requests.Session)

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def counts(self):
        with self.engine.connect() as conn:
            return (
                conn.scalar(select(func.count()).select_from(Data)),
                conn.scalar(select(func.count()).select_from(FileRegister)),
            )

    def import_fixture(self, name="a.csv", content=None):
        content = fixture() if content is None else content
        return sql_write_df(
            self.engine, normalize_csv(content, name).frame, name, content_sha256(content)
        )

    def test_schema_url_and_committed_traceability(self):
        check_schema(self.engine)
        url = database_url({
            "DB_USER": "student", "DB_PASSWORD": "p@ss:/?#", "DB_NAME": "ecobici",
            "DB_HOST": "localhost", "DB_PORT": "5433",
        })
        self.assertEqual(url.port, 5433)
        self.assertEqual(url.password, "p@ss:/?#")
        self.assertEqual(url.drivername, "postgresql+psycopg")
        result = self.import_fixture()
        self.assertEqual(result.status, "imported")
        with self.engine.connect() as conn:
            record = conn.execute(select(FileRegister.__table__)).one()
            trip = conn.execute(select(Data.__table__)).one()
        self.assertEqual(record.row_count, 1)
        self.assertEqual(record.content_sha256, content_sha256(fixture()))
        self.assertEqual(trip.file_register_id, record.id)
        self.assertEqual(trip.bicycle_id, "0007A")

    def test_rollback_after_trips_inserted_also_removes_register(self):
        original_to_sql = pd.DataFrame.to_sql

        def fail_after_insert(frame, *args, **kwargs):
            original_to_sql(frame, *args, **kwargs)
            raise RuntimeError("fallo después de insertar viajes")

        with patch.object(pd.DataFrame, "to_sql", fail_after_insert):
            with self.assertRaisesRegex(RuntimeError, "después de insertar"):
                self.import_fixture()
        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(self.import_fixture().status, "imported")

    def test_rerun_already_imported_never_downloads(self):
        self.import_fixture()
        with patch("data.data_harvest.download_csv") as download:
            summary = run_import(self.engine, self.http, ["https://example.test/a.csv"], self.archive)
        download.assert_not_called()
        self.assertEqual((summary.imported, summary.skipped), (0, 1))
        self.assertEqual(self.import_fixture().status, "already_registered")
        self.assertEqual(self.counts(), (1, 1))

    def test_download_and_transform_failures_do_not_reuse_previous_frame(self):
        urls = [f"https://example.test/{name}.csv" for name in ("a", "broken", "invalid", "b")]
        different = fixture().replace(b"0007A", b"0008B")
        with patch("data.data_harvest.download_csv", side_effect=[
            fixture(), requests.HTTPError("404"), b"no es un CSV", different,
        ]) as download:
            with self.assertLogs("data.data_harvest", level="INFO") as logs:
                summary = run_import(self.engine, self.http, urls, self.archive)
        self.assertEqual((summary.imported, summary.failed), (2, 2))
        self.assertEqual(download.call_count, 4)
        self.assertEqual(self.counts(), (2, 2))
        with self.engine.connect() as conn:
            self.assertEqual(set(conn.scalars(select(FileRegister.file_name))), {"a.csv", "b.csv"})
            self.assertEqual(set(conn.scalars(select(Data.bicycle_id))), {"0007A", "0008B"})
        self.assertTrue(any("broken.csv" in line and "404" in line for line in logs.output))
        self.assertEqual(len(list(self.archive.rglob("*.csv"))), 3)

    def test_hash_match_skips_but_same_row_count_only_reports_suspicion(self):
        self.import_fixture("a.csv")
        same = self.import_fixture("identical.csv")
        self.assertEqual(same.status, "identical_content")
        self.assertEqual(same.related_files, ("a.csv",))
        different = self.import_fixture("other.csv", fixture().replace(b"0007A", b"XYZ"))
        self.assertEqual(different.status, "imported")
        self.assertEqual(different.same_row_count_files, ("a.csv",))
        self.assertEqual(self.counts(), (2, 2))

    def test_identical_bytes_are_reported_before_file_specific_normalization(self):
        self.import_fixture("2021-06.csv", fixture("2021-06.csv"))
        with patch("data.data_harvest.download_csv", return_value=fixture("2021-06.csv")):
            with self.assertLogs("data.data_harvest", level="INFO") as logs:
                summary = run_import(
                    self.engine, self.http, ["https://example.test/copy.csv"], self.archive
                )
        self.assertEqual((summary.skipped, summary.failed), (1, 0))
        self.assertTrue(any("2021-06.csv" in line and "SHA-256" in line for line in logs.output))
        self.assertEqual(self.counts(), (1, 1))

    def test_different_bytes_do_not_prove_different_trips(self):
        self.import_fixture("a.csv")
        # Mismos viajes, encabezado con otras mayúsculas: cambia la huella.
        reformatted = fixture().replace(b"Genero_usuario", b"GENERO_USUARIO")
        result = self.import_fixture("b.csv", reformatted)
        self.assertEqual(result.status, "imported")
        self.assertEqual(self.counts(), (2, 2))

    def test_quality_observations_allow_insert_and_strict_mode_rejects(self):
        urls = ["https://example.test/incomplete.csv"]
        with patch("data.data_harvest.download_csv", return_value=fixture("incomplete.csv")):
            with self.assertLogs("data.data_harvest", level="INFO") as logs:
                summary = run_import(self.engine, self.http, urls, self.archive, strict_quality=True)
            self.assertEqual(summary.failed, 1)
            self.assertEqual(self.counts(), (0, 0))
            with self.assertLogs("data.data_harvest", level="INFO") as logs:
                summary = run_import(self.engine, self.http, urls, self.archive)
        self.assertEqual((summary.imported, summary.quality_issues), (1, 1))
        self.assertTrue(any("Importado:" in line and "con observaciones" in line for line in logs.output))
        self.assertEqual(self.counts(), (2, 1))

    def test_null_markers_import_as_sql_null_with_quality_and_original_preserved(self):
        content = fixture("null_markers.csv")
        with patch("data.data_harvest.download_csv", return_value=content):
            with self.assertLogs("data.data_harvest", level="INFO") as logs:
                summary = run_import(
                    self.engine, self.http, ["https://example.test/null_markers.csv"], self.archive
                )
        self.assertEqual((summary.imported, summary.failed, summary.quality_issues), (1, 0, 1))
        self.assertEqual(self.counts(), (3, 1))
        with self.engine.connect() as conn:
            trips = conn.execute(select(Data.__table__).order_by(Data.id)).all()
        self.assertTrue(all(trip.gender is None and trip.age is None for trip in trips))
        self.assertEqual(trips[2].bicycle_id, "NULL")
        for column in ("gender", "age"):
            self.assertTrue(any(
                f"columna={column}" in line and "cantidad=3" in line and "valor faltante" in line
                for line in logs.output
            ))
        self.assertTrue(any("Importado:" in line and "con observaciones" in line for line in logs.output))
        original = self.archive / content_sha256(content) / "null_markers.csv"
        self.assertEqual(original.read_bytes(), content)

    def test_missing_date_components_insert_as_sql_null_and_preserve_original(self):
        content = fixture("date_null_markers.csv")
        with patch("data.data_harvest.download_csv", return_value=content):
            with self.assertLogs("data.data_harvest", level="INFO") as logs:
                summary = run_import(
                    self.engine, self.http, ["https://example.test/date_null_markers.csv"], self.archive
                )
        self.assertEqual((summary.imported, summary.failed, summary.quality_issues), (1, 0, 1))
        self.assertEqual(self.counts(), (4, 1))
        with self.engine.connect() as conn:
            trips = conn.execute(select(Data.__table__)).all()
        self.assertTrue(all(trip.begin_time is None and trip.end_time is None for trip in trips))
        for column in ("begin_time", "end_time"):
            self.assertTrue(any(
                f"columna={column}" in line and "cantidad=4" in line and "valor faltante" in line
                for line in logs.output
            ))
        original = self.archive / content_sha256(content) / "date_null_markers.csv"
        self.assertEqual(original.read_bytes(), content)

    def test_commit_failure_is_not_announced_as_success(self):
        def fail_commit(connection):
            raise RuntimeError("fallo de commit")

        event.listen(self.engine, "commit", fail_commit)
        try:
            with patch("data.data_harvest.download_csv", return_value=fixture()):
                with self.assertLogs("data.data_harvest", level="INFO") as logs:
                    summary = run_import(
                        self.engine, self.http, ["https://example.test/a.csv"], self.archive
                    )
        finally:
            event.remove(self.engine, "commit", fail_commit)
        self.assertEqual(summary.failed, 1)
        self.assertFalse(any("Importado:" in line for line in logs.output))
        self.assertEqual(self.counts(), (0, 0))


class DownloadTests(unittest.TestCase):
    def test_timeout_and_http_failure_propagate(self):
        session = Mock(spec=requests.Session)
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("404")
        session.get.return_value = Mock(__enter__=Mock(return_value=response), __exit__=Mock(return_value=False))
        with self.assertRaises(requests.HTTPError):
            download_csv(session, "https://example.test/a.csv")
        session.get.assert_called_once_with("https://example.test/a.csv", timeout=(10, 60))

    def test_link_discovery_reuses_session_and_resolves_relative_urls(self):
        session = Mock(spec=requests.Session)
        response = Mock(text='''<a href="/files/a.csv">a</a><a href="https://cdn.test/b.csv?x=1">b</a>
            <a href="/files/a.csv">a</a><a href="/files/archive.zip">zip</a>''')
        session.get.return_value = Mock(__enter__=Mock(return_value=response), __exit__=Mock(return_value=False))
        self.assertEqual(ecobici_links(session), [
            "https://ecobici.cdmx.gob.mx/files/a.csv", "https://cdn.test/b.csv?x=1",
        ])
        self.assertEqual(csv_file_name("https://cdn.test/a.csv?token=1"), "a.csv")


if __name__ == "__main__":
    unittest.main()
