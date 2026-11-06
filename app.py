
import streamlit as st
import plotly.express as px

from src.cdmx_insights.data import load_geography
from src.cdmx_insights.analytics import (
    create_demo_data,
    generate_insight,
)

st.set_page_config(
    page_title="CDMX Insights",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ CDMX Insights Explorer")
st.caption(
    "Explora zonas geográficas y consulta indicadores "
    "asociados a cada selección."
)

try:
    gdf, name_field = load_geography()
except Exception as exc:
    st.error(f"No fue posible cargar la geografía: {exc}")
    st.stop()

# Normalizar la geometría para Plotly.
geojson = gdf.__geo_interface__

# Preparar una tabla con los nombres de las zonas.
zones = gdf["zona"].tolist()

# Datos de demostración; sustituir por datos reales.
metrics = create_demo_data(zones)

# Selector auxiliar para accesibilidad y comprobación.
selected_from_menu = st.selectbox(
    "Selecciona una zona",
    options=["Selecciona en el mapa"] + zones,
    index=0,
)

# Construir el mapa.
fig = px.choropleth_map(
    metrics,
    geojson=geojson,
    locations="zona",
    featureidkey=f"properties.{name_field}",
    color="demanda",
    hover_name="zona",
    hover_data={
        "demanda": True,
        "precio_referencia": True,
        "competencia": True,
    },
    color_continuous_scale="Blues",
    map_style="carto-positron",
    center={"lat": 19.32, "lon": -99.15},
    zoom=8.5,
    opacity=0.7,
)

fig.update_layout(
    height=620,
    margin={"l": 0, "r": 0, "t": 10, "b": 0},
)

# Capturar la selección en el mapa.
event = st.plotly_chart(
    fig,
    use_container_width=True,
    key="cdmx_map",
    on_select="rerun",
    selection_mode="points",
)

selected_zone = None

points = event.selection.get("points", [])

if points:
    point = points[0]

    # Plotly puede exponer la zona mediante location.
    selected_zone = point.get("location")

    # Alternativa si el evento devuelve las propiedades GeoJSON.
    if not selected_zone:
        properties = point.get("properties", {})
        selected_zone = (
            properties.get(name_field)
            or properties.get("zona")
        )

# Si se selecciona desde el menú, también se muestran los datos.
if selected_from_menu != "Selecciona en el mapa":
    selected_zone = selected_from_menu

st.divider()

if selected_zone:
    result = metrics[
        metrics["zona"].str.casefold()
        == str(selected_zone).casefold()
    ]

    if result.empty:
        st.warning(
            "No se encontraron indicadores para la zona seleccionada."
        )
    else:
        row = result.iloc[0]

        st.subheader(f"Insights: {selected_zone}")
        st.caption("Indicadores sintéticos para probar la aplicación.")

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Precio de referencia",
            f'${row["precio_referencia"]:,.0f}',
        )
        col2.metric(
            "Demanda",
            f'{row["demanda"]}/100',
        )
        col3.metric(
            "Competencia",
            f'{row["competencia"]}/100',
        )

        st.markdown("### Análisis de la zona")
        st.info(generate_insight(row))

        st.markdown("### Comparación de indicadores")

        comparison = metrics[
            metrics["zona"] == selected_zone
        ]

        st.bar_chart(
            comparison.set_index("zona")[
                ["demanda", "competencia"]
            ]
        )

        st.caption(
            "Fuente geográfica: portal de datos abiertos de la CDMX. "
            "Los indicadores mostrados son ficticios."
        )
else:
    st.info(
        "Haz clic en una zona del mapa o utiliza el selector "
        "para consultar sus indicadores."
    )
