
import geopandas as gpd
import streamlit as st

GEOJSON_URL = (
    "https://datos.cdmx.gob.mx/dataset/"
    "bae265a8-d1f6-4614-b399-4184bc93e027/resource/"
    "deb5c583-84e2-4e07-a706-1b3a0dbc99b0/download/"
    "deb5c583-84e2-4e07-a706-1b3a0dbc99b0.json"
)


@st.cache_data(ttl=3600)
def load_geography():
    """Descarga y almacena temporalmente la geografía."""
    gdf = gpd.read_file(GEOJSON_URL)

    if gdf.empty:
        raise ValueError("El GeoJSON no contiene registros.")

    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Buscar posibles campos con el nombre de la zona.
    candidates = [
        "NOMGEO",
        "nomgeo",
        "NOMBRE",
        "nombre",
        "NOMBRE_ALC",
        "alcaldia",
        "nomgeo_1",
    ]

    name_field = next(
        (col for col in candidates if col in gdf.columns),
        None,
    )

    if name_field is None:
        raise ValueError(
            "No se identificó la columna del nombre de la zona. "
            f"Columnas disponibles: {gdf.columns.tolist()}"
        )

    gdf = gdf[gdf.geometry.notna()].copy()
    gdf["zona"] = gdf[name_field].astype(str).str.strip()

    return gdf, name_field
