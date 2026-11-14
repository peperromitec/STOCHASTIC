# STOCHASTIC

Análisis de datos de Ecobici (CDMX) con una app en Streamlit.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestor de paquetes y entornos de Python)
- Git

No necesitas instalar Python ni crear un entorno virtual a mano: uv lee
`.python-version` (3.12) y `pyproject.toml` y se encarga de todo.

## Instalación

1. Instala uv:

   ```bash
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Cierra y vuelve a abrir la terminal después de instalarlo.

2. Clona el repositorio e instala las dependencias:

   ```bash
   git clone https://github.com/peperromitec/STOCHASTIC.git
   cd STOCHASTIC
   uv sync
   ```

   `uv sync` crea el entorno `.venv` e instala las versiones exactas de
   `uv.lock`, así todos trabajamos con lo mismo.

## Uso

Siempre ejecuta los comandos con `uv run` para que usen el entorno del proyecto:

```bash
# App de Streamlit
uv run streamlit run app.py

# Cualquier script
uv run python ruta/al/script.py
```

**Notebooks:** abre `stage1.ipynb` en VS Code y selecciona el kernel
`.venv` (Python 3.12) arriba a la derecha.

## Datos

Los archivos de viajes de Ecobici ya vienen incluidos en `data/`
(`2025-10.csv.gz`, `2026-10.csv.gz`), así que el notebook y la app corren
sin instalar nada más. No hace falta descomprimirlos: pandas los lee
directamente con `pd.read_csv("data/2025-10.csv.gz")`.

## Recolector de datos (carpeta `data/`)

El recolector es **opcional**: descarga el histórico completo de Ecobici y lo
guarda en PostgreSQL. No lo necesitas para correr el notebook.

Para usarlo:

1. Instala PostgreSQL y crea la base de datos `ecobici`.
2. Copia `.env.example` a `.env` y llena tus credenciales (`DB_USER`,
   `DB_PASSWORD`, `DB_NAME`).
3. Ejecuta `uv run python data/data_harvest.py` desde la carpeta `data/`.

El archivo `.env` contiene credenciales: **nunca lo subas al repositorio**.

## Agregar dependencias

No uses `pip install` ni `requirements.txt`. Usa:

```bash
uv add <paquete>
```

Esto actualiza `pyproject.toml` y `uv.lock`; haz commit de ambos para que el
resto del equipo los reciba con `uv sync`.

## Problemas comunes

- **`ModuleNotFoundError`**: corre `uv sync` (alguien agregó dependencias nuevas).
- **`command not found: uv`**: reinicia la terminal tras instalar uv.
- **Después de un `git pull`**: vuelve a correr `uv sync`.
- **VS Code pide instalar `ipykernel`**: no le des "Instalar"; cambia el kernel a `.venv`.
