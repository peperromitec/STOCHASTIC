"""Integración opcional. Nunca lee .env y exige una base ecobici_test_*.

ECOBICI_TEST_DATABASE_URL debe apuntar a una base aislada creada expresamente.
Cada prueba usa su propio esquema; solo ese esquema se elimina al terminar.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import threading
import unittest
import uuid

import pandas as pd
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError

from data.database import check_schema
from data.normalization import normalize_csv
from data.request import content_sha256
from data.schemas.data_model import Data
from data.schemas.file_register_model import FileRegister
from data.sql_writer import sql_write_df

ROOT = Path(__file__).resolve().parents[1]
TEST_URL = os.environ.get("ECOBICI_TEST_DATABASE_URL")


@unittest.skipUnless(TEST_URL, "PostgreSQL aislado no configurado")
class PostgreSQLTests(unittest.TestCase):
    def setUp(self):
        self.admin = create_engine(TEST_URL)
        if not (self.admin.url.database or "").startswith("ecobici_test_"):
            self.admin.dispose()
            raise ValueError("La base de pruebas debe llamarse ecobici_test_*")
        self.schema = "test_" + uuid.uuid4().hex
        with self.admin.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        self.engine = create_engine(
            TEST_URL, connect_args={"options": f"-csearch_path={self.schema}"},
        )
        with self.engine.begin() as conn:
            conn.exec_driver_sql('''CREATE TABLE file_register (
                id SERIAL PRIMARY KEY, file_name VARCHAR(255) UNIQUE, process_date TIMESTAMP
            )''')
            conn.exec_driver_sql('''CREATE TABLE data (
                id SERIAL PRIMARY KEY, gender VARCHAR(1), age INTEGER, bicycle_id INTEGER,
                begin_station INTEGER, end_station INTEGER,
                begin_time TIMESTAMP, end_time TIMESTAMP
            )''')
            conn.exec_driver_sql("INSERT INTO file_register (file_name) VALUES ('old.csv')")
            conn.exec_driver_sql('''INSERT INTO data
                (gender, age, bicycle_id, begin_station, end_station, begin_time, end_time)
                VALUES ('M', 25, 7, 1, 2, '2020-01-01 10:00', '2020-01-01 10:10'),
                       ('M', 25, 7, 1, 2, '2020-01-01 10:00', '2020-01-01 10:10')
            ''')

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as conn:
            # Nombre aleatorio generado por esta prueba, dentro de la base aislada.
            conn.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')
        self.admin.dispose()

    def script(self, relative_path):
        raw = self.engine.raw_connection()
        try:
            raw.driver_connection.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute((ROOT / relative_path).read_text(), prepare=False)
                results = []
                while True:
                    if cursor.description:
                        results.append(cursor.fetchall())
                    if not cursor.nextset():
                        break
                return results
        finally:
            raw.driver_connection.rollback()
            raw.driver_connection.autocommit = False
            raw.close()

    def migrate(self):
        self.script("migrations/001_import_traceability.sql")

    def import_sample(self, name="sample.csv", content=None):
        if content is None:
            content = (ROOT / "tests/fixtures/aliases.csv").read_bytes()
        return sql_write_df(
            self.engine, normalize_csv(content, name).frame, name, content_sha256(content)
        )

    def counts(self):
        with self.engine.connect() as conn:
            return (
                conn.scalar(select(func.count()).select_from(Data)),
                conn.scalar(select(func.count()).select_from(FileRegister)),
            )

    def test_migration_preserves_history_and_supports_new_identifiers(self):
        self.migrate()
        self.migrate()
        check_schema(self.engine)
        with self.engine.connect() as conn:
            history = conn.execute(select(Data.__table__).order_by(Data.id)).all()
            register = conn.execute(select(FileRegister.__table__)).one()
        self.assertEqual([row.id for row in history], [1, 2])
        self.assertEqual([row.bicycle_id for row in history], ["7", "7"])
        self.assertEqual([row.begin_station for row in history], ["1", "1"])
        self.assertTrue(all(row.file_register_id is None for row in history))
        self.assertIsNone(register.row_count)
        self.assertIsNone(register.content_sha256)
        result = self.import_sample()
        self.assertEqual((result.status, result.row_count), ("imported", 1))
        with self.engine.connect() as conn:
            trip = conn.execute(select(Data.__table__).where(Data.file_register_id == result.register_id)).one()
        self.assertEqual((trip.bicycle_id, trip.begin_station, trip.end_station), ("0007A", "001", "271-272"))
        self.assertEqual(self.counts(), (3, 2))

    def test_real_constraint_failure_rolls_back_register_and_trips(self):
        self.migrate()
        with self.engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE data ADD CHECK (age >= 0)")
        content = (ROOT / "tests/fixtures/aliases.csv").read_bytes().replace(b"M,25,", b"M,-1,")
        # pandas 3.1 envuelve errores de SQLAlchemy en DatabaseError.
        with self.assertRaises((IntegrityError, pd.errors.DatabaseError)):
            self.import_sample(content=content)
        self.assertEqual(self.counts(), (2, 1))
        self.assertEqual(self.import_sample().status, "imported")
        self.assertEqual(self.counts(), (3, 2))

    def test_concurrent_same_name_has_only_one_load(self):
        self.migrate()
        barrier = threading.Barrier(2)
        seen = threading.local()

        def synchronize_first_lookup(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("SELECT file_register.id") and not getattr(seen, "done", False):
                seen.done = True
                barrier.wait(timeout=10)

        event.listen(self.engine, "after_cursor_execute", synchronize_first_lookup)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda _: self.import_sample(), range(2)))
        finally:
            event.remove(self.engine, "after_cursor_execute", synchronize_first_lookup)
        self.assertEqual(sorted(result.status for result in results), ["already_registered", "imported"])
        self.assertEqual(self.counts(), (3, 2))

    def test_audit_is_read_only_and_reports_full_attribute_candidates(self):
        legacy = self.script("audit/legacy_import_audit.sql")
        self.assertEqual(legacy[1], [(2,)])
        self.assertEqual(legacy[-1][0][7], 2)
        self.migrate()
        before = self.counts()
        results = self.script("audit/import_audit.sql")
        self.assertEqual(results[0], [(2, 2)])
        self.assertEqual(results[-1][0][7], 2)  # occurrences, tras los siete atributos
        self.assertEqual(self.counts(), before)

    def test_explicit_dates_fractional_seconds_and_nulls_survive_insertion(self):
        self.migrate()
        dates = (ROOT / "tests/fixtures/dates.csv").read_bytes()
        result = self.import_sample("dates.csv", dates)
        with self.engine.connect() as conn:
            trips = conn.execute(
                select(Data.__table__).where(Data.file_register_id == result.register_id)
                .order_by(Data.id)
            ).all()
        self.assertEqual(trips[0].begin_time.isoformat(), "2021-04-03T09:10:11.123456")
        self.assertEqual(trips[0].end_time.isoformat(), "2021-04-03T09:12:00.500000")
        self.assertEqual(trips[1].begin_time.isoformat(), "2021-12-11T23:59:59")
        incomplete = (ROOT / "tests/fixtures/incomplete.csv").read_bytes()
        result = self.import_sample("incomplete.csv", incomplete)
        with self.engine.connect() as conn:
            trips = conn.execute(
                select(Data.__table__).where(Data.file_register_id == result.register_id)
                .order_by(Data.id)
            ).all()
        self.assertEqual(len(trips), 2)
        self.assertEqual(trips[0].bicycle_id, "NULL")
        self.assertIsNone(trips[0].age)
        self.assertLess(trips[0].end_time, trips[0].begin_time)
        self.assertIsNone(trips[1].bicycle_id)
        self.assertIsNone(trips[1].begin_time)

    def test_gender_and_age_null_markers_fit_existing_nullable_schema(self):
        self.migrate()
        content = (ROOT / "tests/fixtures/null_markers.csv").read_bytes()
        result = self.import_sample("null_markers.csv", content)
        self.assertEqual((result.status, result.row_count), ("imported", 3))
        with self.engine.connect() as conn:
            trips = conn.execute(
                select(Data.__table__).where(Data.file_register_id == result.register_id)
                .order_by(Data.id)
            ).all()
        self.assertEqual(len(trips), 3)
        self.assertTrue(all(trip.gender is None and trip.age is None for trip in trips))
        self.assertEqual(trips[2].bicycle_id, "NULL")

    def test_two_digit_year_dates_and_null_components_survive_insertion(self):
        self.migrate()
        content = (ROOT / "tests/fixtures/date_formats.csv").read_bytes()
        result = self.import_sample("202209.csv", content)
        with self.engine.connect() as conn:
            trips = conn.execute(
                select(Data.__table__).where(Data.file_register_id == result.register_id)
                .order_by(Data.id)
            ).all()
        self.assertEqual(result.row_count, 4)
        self.assertEqual(trips[0].begin_time.isoformat(), "2022-08-30T08:00:00")
        self.assertEqual(trips[0].end_time.isoformat(), "2022-08-30T08:15:00")
        self.assertEqual(trips[1].begin_time.isoformat(), "2022-08-31T23:59:59.123456")
        self.assertEqual(trips[1].end_time.isoformat(), "2022-09-01T00:15:00")
        content = (ROOT / "tests/fixtures/date_null_markers.csv").read_bytes()
        result = self.import_sample("date_null_markers.csv", content)
        with self.engine.connect() as conn:
            trips = conn.execute(
                select(Data.__table__).where(Data.file_register_id == result.register_id)
            ).all()
        self.assertEqual(result.row_count, 4)
        self.assertTrue(all(trip.begin_time is None and trip.end_time is None for trip in trips))

    def test_single_digit_hours_with_fractions_survive_insertion(self):
        self.migrate()
        content = (ROOT / "tests/fixtures/clock_formats.csv").read_bytes()
        result = self.import_sample("clocks.csv", content)
        with self.engine.connect() as conn:
            trips = conn.execute(
                select(Data.__table__).where(Data.file_register_id == result.register_id)
                .order_by(Data.id)
            ).all()
        self.assertEqual(result.row_count, 4)
        self.assertEqual(trips[0].begin_time.isoformat(), "2021-04-03T00:05:06")
        self.assertEqual(trips[1].begin_time, trips[0].begin_time)
        self.assertEqual(trips[2].begin_time.isoformat(), "2021-04-03T00:05:06.100000")
        self.assertEqual(trips[2].end_time.isoformat(), "2021-04-03T00:10:11.120000")
        self.assertEqual(trips[3].begin_time.isoformat(), "2021-04-03T00:05:06.123456")


if __name__ == "__main__":
    unittest.main()
