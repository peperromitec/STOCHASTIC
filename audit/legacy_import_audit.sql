-- Compatible con el esquema anterior a la migración 001. Solo lectura.
BEGIN TRANSACTION READ ONLY;

SELECT id, file_name, process_date FROM file_register ORDER BY process_date, id;
SELECT count(*) AS total_trips FROM data;

-- Se comparan los siete atributos del viaje. Son candidatos para revisión,
-- no prueba de duplicación. Las filas antiguas no identifican su archivo.
SELECT gender, age, bicycle_id, begin_station, end_station, begin_time, end_time,
       count(*) AS occurrences, min(id) AS first_id, max(id) AS last_id
FROM data
GROUP BY gender, age, bicycle_id, begin_station, end_station, begin_time, end_time
HAVING count(*) > 1
ORDER BY occurrences DESC, min(id)
LIMIT 100;

COMMIT;
