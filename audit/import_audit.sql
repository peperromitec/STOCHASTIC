-- PostgreSQL. Solo lectura; puede recorrer toda data. LIMIT acota la salida,
-- pero no el trabajo del GROUP BY. Ejecutar sobre la base elegida expresamente.
BEGIN TRANSACTION READ ONLY;

-- Historia sin procedencia conocida; no se puede asignar a archivos por tamaño.
SELECT count(*) AS total_trips,
       count(*) FILTER (WHERE file_register_id IS NULL) AS trips_without_provenance
FROM data;

SELECT id, file_name, process_date, row_count, content_sha256
FROM file_register
ORDER BY process_date, id;

-- Contrastar el conteo declarado con los viajes efectivamente vinculados.
SELECT f.id, f.file_name, f.process_date, f.row_count,
       count(d.id) AS linked_rows,
       CASE WHEN f.row_count IS NULL THEN 'conteo histórico desconocido'
            WHEN f.row_count = count(d.id) THEN 'conteo consistente'
            ELSE 'revisar diferencia de conteo' END AS review
FROM file_register f
LEFT JOIN data d ON d.file_register_id = f.id
GROUP BY f.id, f.file_name, f.process_date, f.row_count
ORDER BY f.id;

-- Coincidencia exacta de los bytes originales, si se conoce la huella.
SELECT content_sha256, array_agg(file_name ORDER BY file_name) AS related_files
FROM file_register
WHERE content_sha256 IS NOT NULL
GROUP BY content_sha256 HAVING count(*) > 1;

-- Mismo tamaño: solo sospecha. Nunca usarlo como prueba ni para hacer backfill.
SELECT row_count, array_agg(file_name ORDER BY file_name) AS same_size_files
FROM file_register
WHERE row_count IS NOT NULL
GROUP BY row_count HAVING count(*) > 1;

-- Candidatos por TODOS los atributos disponibles del viaje, excepto la PK y
-- la procedencia. Aun así pueden ser viajes legítimos distintos. No hay un
-- identificador único del viaje en el CSV; estación y hora no son suficientes.
SELECT gender, age, bicycle_id, begin_station, end_station, begin_time, end_time,
       count(*) AS occurrences, min(id) AS first_id, max(id) AS last_id,
       count(DISTINCT file_register_id) AS known_source_files,
       count(*) FILTER (WHERE file_register_id IS NULL) AS unknown_source_rows
FROM data
GROUP BY gender, age, bicycle_id, begin_station, end_station, begin_time, end_time
HAVING count(*) > 1
ORDER BY occurrences DESC, min(id)
LIMIT 100;

COMMIT;
