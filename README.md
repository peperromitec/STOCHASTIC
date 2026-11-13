# STOCHASTIC · importación de Ecobici

El importador descarga CSV, conserva sus bytes originales, normaliza encabezados
y tipos, reporta calidad y guarda cada archivo en una transacción independiente.
Se ejecuta desde la raíz del repositorio como módulo de Python.

## Configuración

Python >= 3.12 y PostgreSQL. Para el importador, las dependencias están en
`requirements.txt`; `pyproject.toml` y `uv.lock` corresponden a la aplicación
Streamlit. No hacen falta frameworks de migración ni de pruebas.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Editar `.env` con `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` y `DB_NAME`.
Se usa `postgresql+psycopg` y `URL.create`, que conserva contraseñas con caracteres
como `@`, `/` o `:` sin interpolarlas en una URL. La ejecución reutiliza un motor
y una `requests.Session`, y cierra ambos incluso si ocurre un error.

## Base existente y migración

Los modelos están en `data/schemas`. `create_all()` solo sirve para una base
nueva: **no actualiza tablas existentes**. El importador revisa el esquema al
arrancar y falla antes de descargar si falta la migración.

`migrations/001_import_traceability.sql` se prepara para ejecución manual:

- Convierte `bicycle_id`, `begin_station` y `end_station` a `TEXT` mediante cast.
- Agrega `file_register.row_count BIGINT`, `content_sha256 VARCHAR(64)` y
  `data.file_register_id INTEGER REFERENCES file_register(id)`, todos anulables.
- Conserva `UNIQUE(file_name)` y agrega índices para la huella y la FK.
- No borra filas ni asigna procedencia, conteos o huellas a cargas antiguas.

El script usa una única transacción. Los `ALTER TABLE` toman bloqueos y la
conversión puede requerir reescribir la tabla; revisar y programar su ejecución
según el tamaño de la base. Convertir un entero existente a texto tampoco puede
recuperar ceros iniciales que una carga anterior ya perdió.

**Aplicar a una base real requiere autorización expresa.** Este comando es una
instrucción de ejecución, no una acción automática del importador:

```bash
# Configurar PGHOST, PGPORT, PGUSER y PGDATABASE para la base elegida.
# psql usa estas variables (no carga las variables DB_* de .env).
# Puede solicitar la contraseña o usar ~/.pgpass.
psql -X -v ON_ERROR_STOP=1 -f migrations/001_import_traceability.sql
```

Para una base nueva, vacía y elegida expresamente, se pueden crear las tablas
con los modelos. El siguiente código rechaza una base que ya contenga tablas:

```bash
python - <<'PY'
from dotenv import load_dotenv
from sqlalchemy import inspect
from data.database import create_db_engine
from data.schemas.base import Base

load_dotenv()
engine = create_db_engine()
try:
    with engine.begin() as connection:
        if inspect(connection).get_table_names():
            raise RuntimeError("La base debe estar vacía; para datos existentes usa la migración")
        Base.metadata.create_all(connection)
finally:
    engine.dispose()
PY
```

## Ejecución

```bash
# Elegir uno o varios CSV. No inicia una descarga histórica por defecto.
python -m data.data_harvest --url 'https://servidor/ruta/2021-06.csv'
python -m data.data_harvest --url 'https://servidor/a.csv' --url 'https://servidor/b.csv'

# Rechazar archivos con observaciones de calidad, conservando su original.
python -m data.data_harvest --url 'https://servidor/a.csv' --strict-quality

# Solo si se desea procesar todos los enlaces CSV publicados en el portal:
python -m data.data_harvest --discover
```

Los ZIP quedan fuera del descubrimiento; no se descomprimen automáticamente.
Los originales se guardan en `downloads/ecobici/<sha256>/<file_name>`; cambiar
esa raíz con `--archive-dir RUTA`. Se conservan también los CSV descargados que
fallen al transformarse. Esta carpeta se excluye de Git.

Antes de descargar se consulta `file_name`. Si ya existe, se omite incluso si la
URL pudiera haber cambiado: reemplazar una carga requiere revisión manual.
Tras la descarga se calcula SHA-256. Si los bytes coinciden con otra carga, se
informan sus nombres y se omite la nueva carga sin crear otro registro. La
transacción vuelve a comprobar nombre y huella; el `UNIQUE` resuelve carreras
por el mismo nombre sin dejar datos parciales. La huella tiene un índice no
único: no ofrece exclusión mutua entre procesos para nombres diferentes.

La transacción crea el registro, obtiene su id, inserta los viajes con ese id
usando **la misma conexión**, cuenta las filas vinculadas y guarda ese conteo.
Solo después del commit se informa `Importado`. Un fallo revierte registro y
viajes, informa URL, archivo y causa y continúa con el siguiente archivo.
El comando devuelve código 1 si algún archivo falla y 0 si todos se importan
o se omiten por estar registrados o tener bytes idénticos.

Un mismo `row_count` solo produce una observación; no impide importar. Huellas
distintas **no garantizan viajes distintos**: cambios de encabezados, orden,
codificación o formato producen otros bytes. No se realiza deduplicación lógica
automática. Conviene revisar observaciones y auditoría antes de cargar variantes
del mismo período.

## Normalización y calidad

`data/normalization.py` centraliza los alias, elimina BOM, normaliza espacios y
mayúsculas de encabezados, y detecta colisiones o columnas requeridas ausentes.
`Bici`, estaciones y demás campos se leen como texto desde el principio.
Se conservan códigos alfanuméricos, ceros iniciales y estaciones como `271-272`.
Las celdas vacías o compuestas de blancos se consideran faltantes. Además, en
`gender`, `age` y las cuatro columnas de fecha y hora de retiro y arribo, el
marcador literal `NULL` se convierte a `pd.NA`, ignorando mayúsculas y espacios
externos, antes de convertir tipos o validar. Se reporta como faltante mediante
el sistema de calidad existente y puede insertarse como SQL `NULL` en las
columnas anulables del esquema. Los identificadores y estaciones
conservan códigos como `NULL` o `NA`; otros valores desconocidos no se convierten
a faltantes. La edad debe ser un entero o un faltante; valores no representables
en el esquema producen un error, sin truncarse. El CSV original se conserva.

Se admiten explícitamente fechas `DD/MM/YYYY` (`%d/%m/%Y`), `DD/MM/YY` (`%d/%m/%y`)
y `YYYY-MM-DD` (`%Y-%m-%d`), tanto para retiro como para arribo, y horas
`H:MM:SS` o `HH:MM:SS` con una fracción opcional de 1 a 6 dígitos (precisión de
PostgreSQL). Las horas deben estar entre 0 y 23, y minutos y segundos entre 0 y
59; se rechazan `24:00:00` y los segundos 60 sin permitir que pandas los ajuste.
No se usa `format="mixed"`
ni `errors="coerce"`. Un valor no vacío inválido informa archivo, columna y
ejemplos. Se validan fecha y hora por separado; si falta una parte, el timestamp
queda `NULL`. No se cambian fechas ni se infieren cruces de medianoche. Las horas
se almacenan sin conversión de zona, como los timestamps originales del esquema;
`process_date` registra la hora UTC sin zona.

La corrección de junio de 2021 solo se aplica a `2021-06.csv` con los nueve
campos conocidos, en su orden habitual, cuando el último encabezado repite
`Hora_Retiro` (o aparece como `Hora_Retiro.1`). Cualquier otra estructura requiere
revisión y falla en lugar de aplicar esa corrección por conjetura.

`BikeID` no se equipara a `Bici`: se excluye del análisis con una observación y
se conserva en el original. Otras columnas ajenas al esquema también se enumeran
al excluirlas; nunca sustituyen columnas conocidas. La lectura es CSV separado
por comas y UTF-8, con BOM opcional; otros formatos fallan explícitamente.

`data/validation.py` reporta faltantes, edades negativas y arribos anteriores al
retiro sin eliminar filas ni corregir valores. Por defecto se importan esos
viajes y el resultado dice `calidad=con observaciones`. `--strict-quality` evita
importar ese archivo completo. `validaciones superadas` solo significa que no
se encontraron esas anomalías; poder insertar no certifica la calidad ni la
ausencia de viajes repetidos.

## Auditoría de solo lectura

No es necesario migrar primero para revisar las cargas antiguas:

```bash
psql -X -v ON_ERROR_STOP=1 -f audit/legacy_import_audit.sql
# Después de aplicar la migración, incluye huellas y conteos vinculados:
psql -X -v ON_ERROR_STOP=1 -f audit/import_audit.sql
```

Ambos scripts usan `BEGIN TRANSACTION READ ONLY`. Revisan el registro de archivos
y agrupan candidatos repetidos por los **siete atributos disponibles del viaje**,
sin usar solo estación y hora. Incluso una igualdad completa requiere revisión:
no se dispone de un identificador original único del viaje. La salida de grupos
se limita a 100, pero la consulta puede recorrer toda la tabla.

La auditoría posterior a la migración compara conteos declarados y vinculados,
lista archivos con SHA-256 común, separa la sospecha por `row_count` y cuantifica
viajes sin procedencia. Los viajes antiguos con `file_register_id NULL` no se
pueden atribuir de forma fiable a un CSV ni reconstruir mediante `row_count`,
fechas de proceso, rangos de id o tamaños coincidentes. Tampoco es posible
calcular la huella original de un archivo a partir de los viajes guardados.
Ninguna consulta elimina duplicados o registros ni rellena procedencia.

Para investigar filas con múltiples faltantes directamente en un original local:

```bash
python -m data.audit_csv /ruta/al/original/2021-08.csv
```

Este comando solo lee el CSV, registra su SHA-256 y cuenta filas con al menos
dos de los siete campos de análisis faltantes, usando la política de marcadores
del importador. Desglosa esas filas entre totalmente vacías, compuestas solo de
blancos o marcadores `NULL`, y parcialmente pobladas. Examina todas las columnas
del original, incluidas las que no se importan, y muestra números de fila y
nombres de campos poblados como ejemplos. También informa cuántas filas tienen
los siete campos de análisis faltantes: ese conteo puede incluir filas que sí
contenían una fecha u hora aislada en el original. No valida el formato de los
valores presentes ni los reclasifica como faltantes; no descarga, inserta,
elimina ni modifica archivos o datos en la base.

Si una carga anterior no conservó el archivo, se puede recuperar únicamente el
CSV mensual del portal oficial para inspeccionarlo sin reimportarlo. Se hizo
esta comprobación para agosto de 2021: las 11,084 filas con múltiples faltantes
son registros de nueve campos vacíos al final del archivo. El
[informe de 2021-08](audit/2021-08_quality_report.md) incluye los conteos, la
fuente y la huella de la copia examinada, sin asumir que coincida byte a byte
con una descarga histórica cuya huella no se guardó.

## Pruebas

Sin red, sin descargar el histórico y sin leer las credenciales de `.env`:

```bash
python -m unittest discover -s tests -v
```

Usan fixtures CSV pequeños y SQLite en memoria para comprobar normalización,
fallos entre archivos, rollback, commit fallido, conteos, huellas y reejecución.
Las pruebas PostgreSQL se omiten salvo que se configure expresamente
`ECOBICI_TEST_DATABASE_URL`, cuya base debe llamarse `ecobici_test_*`. Cada prueba
crea y elimina únicamente su esquema aleatorio dentro de esa base de pruebas.
También comprueban conservación de historia al migrar, restricciones reales,
concurrencia por nombre y ejecución de ambas auditorías.

Ejemplo para crear un servidor de pruebas temporal en Linux con los binarios
`initdb`, `pg_ctl` y `createdb` en `PATH`, sin usar una base existente ni TCP:

```bash
PG_TEST_ROOT=$(mktemp -d /tmp/ecobici-test.XXXXXXXX)
initdb -D "$PG_TEST_ROOT/db" -U ecobici_test -A trust --no-locale --encoding=UTF8
pg_ctl -D "$PG_TEST_ROOT/db" -l "$PG_TEST_ROOT/server.log" \
  -o "-h '' -k $PG_TEST_ROOT -p 55432 -c unix_socket_permissions=0700" -w start
createdb -h "$PG_TEST_ROOT" -p 55432 -U ecobici_test ecobici_test_import
ECOBICI_TEST_DATABASE_URL="postgresql+psycopg://ecobici_test@/ecobici_test_import?host=$PG_TEST_ROOT&port=55432" \
  python -m unittest discover -s tests -v
pg_ctl -D "$PG_TEST_ROOT/db" -m fast -w stop
```
