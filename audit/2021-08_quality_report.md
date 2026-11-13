# Auditoría de 2021-08.csv

Se descargó únicamente el [CSV oficial de agosto de 2021](https://ecobici.cdmx.gob.mx/wp-content/uploads/2022/07/2021-08.csv),
enlazado por el [portal de datos abiertos de Ecobici](https://ecobici.cdmx.gob.mx/datos-abiertos/),
el 13 de noviembre de 2026. No se consultó ni modificó la base de datos y no se
ejecutó una importación. Los bytes originales se conservaron en
`downloads/ecobici/9232c499dad9c9578434835afb6830f0ea1b55c5dd9409aa5dd8818b0258abfb/2021-08.csv`.

Tamaño: **20,248,095 bytes**. SHA-256:
`9232c499dad9c9578434835afb6830f0ea1b55c5dd9409aa5dd8818b0258abfb`.
Los resultados completos están en [2021-08_quality_report.json](2021-08_quality_report.json).

| Clasificación | Filas |
| --- | ---: |
| Total de registros de datos, sin encabezado | 354,267 |
| Registros con al menos dos campos de análisis faltantes | 11,084 |
| De ese grupo: nueve campos originales vacíos | **11,084** |
| De ese grupo: solo blancos o marcadores NULL, sin ser totalmente vacíos | 0 |
| De ese grupo: parcialmente poblados | **0** |
| Registros restantes, con algún dato original | 343,183 |
| Registros con únicamente gender faltante | 7,724 |

Las **11,084 filas están al final del archivo**, desde el registro CSV 343,185
hasta el 354,268, contando el encabezado como registro 1. Cada una contiene
nueve campos vacíos; no son líneas físicas sin campos. El último registro
poblado es el 343,184 y no hay registros poblados después del primero vacío.

Se midió la presencia de los nueve campos originales antes de combinar fecha y
hora. Esto evita concluir que un registro era vacío solo porque sus siete
campos de análisis acabaran en NULL. Para este archivo ambos conteos coinciden:
las 11,084 filas del grupo están vacías también en el original. La cifra de
faltantes de gender es 18,808 porque incluye esas 11,084 filas y otros 7,724
registros que sí contienen el resto de sus datos.

También se ejecutó la normalización y validación **solo en memoria** sobre este
CSV: conservó las 354,267 filas, convirtió las fechas y horas sin errores y
reportó los faltantes mediante las siete observaciones de calidad registradas
en el JSON. No se eliminaron filas ni se insertaron viajes.

La conclusión corresponde a esta copia oficial y su huella. Sin comparar esa
huella con la de la carga previa, no se puede garantizar identidad byte a byte
con lo que se descargó entonces. Tampoco se verificó qué filas están actualmente
en la base ni se reconstruyó procedencia histórica.

Para repetir la inspección local sin acceder a la base:

```bash
python -m data.audit_csv downloads/ecobici/9232c499dad9c9578434835afb6830f0ea1b55c5dd9409aa5dd8818b0258abfb/2021-08.csv
```
