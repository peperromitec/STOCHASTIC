-- Solo ejecutar expresamente sobre la base elegida. No lo ejecuta el importador.
-- PostgreSQL: si algo falla, se revierte la migración completa.
BEGIN;

ALTER TABLE data
    ALTER COLUMN bicycle_id TYPE TEXT USING bicycle_id::text,
    ALTER COLUMN begin_station TYPE TEXT USING begin_station::text,
    ALTER COLUMN end_station TYPE TEXT USING end_station::text;

-- Sin DEFAULT ni backfill: la procedencia de filas antiguas es desconocida.
ALTER TABLE file_register
    ADD COLUMN IF NOT EXISTS row_count BIGINT,
    ADD COLUMN IF NOT EXISTS content_sha256 VARCHAR(64);
ALTER TABLE data ADD COLUMN IF NOT EXISTS file_register_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'data'::regclass
          AND conname = 'fk_data_file_register'
    ) THEN
        ALTER TABLE data ADD CONSTRAINT fk_data_file_register
            FOREIGN KEY (file_register_id) REFERENCES file_register(id);
    END IF;
END $$;

-- Conserva el UNIQUE(file_name) existente. No elimina registros en conflicto.
CREATE UNIQUE INDEX IF NOT EXISTS ux_file_register_file_name
    ON file_register(file_name);
CREATE INDEX IF NOT EXISTS ix_file_register_content_sha256
    ON file_register(content_sha256);
CREATE INDEX IF NOT EXISTS ix_data_file_register_id ON data(file_register_id);

COMMIT;
