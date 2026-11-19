import streamlit as st
import pandas as pd
import pydeck as pdk


st.title("🗺️ CDMX Insights Explorer")

col1, col2 = st.columns(2)
with col1:
    st.pydeck_chart(
    pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        initial_view_state=pdk.ViewState(
            latitude=19.4326,
            longitude=-99.1332,
            zoom=11,
            pitch=0,
        ),
    )
)
with col2:
    option = st.selectbox("De cuál estación quieres iniciar tu análisis",("Option 1", "Option 2", "Option 3"))
    option2 = st.selectbox("A cuál estación quieres llegar",("Option 1", "Option 2", "Option 3"))
    option3 = st.selectbox("Análisis a lo largo del tiempo",("Hoy", "Semana", "Mes", "Año","Personalizado"))
    sub1, sub2 = st.columns(2)
    
    with sub1:
        st.metric("Estación Inicio", option)
        st.metric("Frecuencia de viajes", "14,520", "+12%")
        st.metric("Duración promedio", "18 min", "-2 min")
        
        
    with sub2:
        st.metric("Estación Fin", option2)
        st.metric("Distancia Prom.", "3.4 km", "+0.3 km")
        st.metric("Ahorro de CO2", "4,120", "+85")
        







