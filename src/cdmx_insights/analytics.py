
import pandas as pd


def create_demo_data(zones):
    """Genera datos ficticios para probar la interfaz."""

    rows = []

    for i, zone in enumerate(zones):
        rows.append({
            "zona": zone,
            "precio_referencia": 100 + i * 10,
            "demanda": 50 + (i * 7) % 50,
            "competencia": 40 + (i * 11) % 60,
        })

    return pd.DataFrame(rows)


def generate_insight(row):
    """Genera una descripción ilustrativa de los indicadores."""

    if row["demanda"] >= 80:
        demand_text = "demanda elevada"
    elif row["demanda"] >= 60:
        demand_text = "demanda intermedia"
    else:
        demand_text = "demanda relativamente baja"

    if row["competencia"] >= 75:
        competition_text = "competencia elevada"
    else:
        competition_text = "competencia moderada"

    return (
        f"En este escenario de demostración se observa "
        f"{demand_text} y {competition_text}. "
        "Estos indicadores son sintéticos, no estadísticas reales."
    )
