import streamlit as st
import pandas as pd
import json

# ==== Cargar datos ====
with open("noticias.json", "r", encoding="utf-8") as f:
    noticias = json.load(f)

with open("zonas.json", "r", encoding="utf-8") as f:
    zonas = json.load(f)

# Normalizar datos
df_noticias = pd.json_normalize(noticias)
df_zonas = pd.json_normalize(
    zonas,
    record_path=["entidades", "zonas_produccion"],
    meta=["id", "fuente", "titulo",
          ["entidades", "producto"],
          ["entidades", "variedad"]]
)

# ==== Sidebar de filtros ====
st.sidebar.title("Filtros")
variedades = sorted(df_noticias["entidades.variedad"].dropna().unique())
variedad_sel = st.sidebar.selectbox("Selecciona variedad", variedades)

# Filtrar noticias por variedad
df_filtrado = df_noticias[df_noticias["entidades.variedad"] == variedad_sel]

# ==== Mostrar noticias ====
st.title("📊 Cuadro de mandos agrícola")
st.subheader(f"Variedad seleccionada: {variedad_sel}")

st.write("### Noticias relacionadas")
if not df_filtrado.empty:
    st.dataframe(df_filtrado[[
        "fecha_recogida",
        "fuente",
        "titulo",
        "entidades.pais",
        "entidades.region",
        "entidades.producto",
        "entidades.variedad",
        "nivel",
        "razon"
    ]])
else:
    st.info("No hay noticias para esta variedad.")

# ==== Cruce con zonas de producción ====
st.write("### Zonas de producción y noticias en el mapa")

producto = df_filtrado["entidades.producto"].iloc[0] if not df_filtrado.empty else None
zonas_rel = df_zonas[
    (df_zonas["entidades.variedad"] == variedad_sel) |
    (df_zonas["entidades.producto"] == producto)
]

# Preparar datos de mapa
map_points = []

if not zonas_rel.empty:
    for _, row in zonas_rel.iterrows():
        map_points.append({
            "lat": row["coordenadas.lat"],
            "lon": row["coordenadas.lon"],
            "tipo": "Zona",
            "pais": row["pais"],
            "region": row["region"],
            "producto": row["entidades.producto"],
            "variedad": row["entidades.variedad"],
            "volumen_tn": row["volumen_estimado_tn"],
            "periodo_inicio": row["periodo_produccion.inicio_mes"],
            "periodo_fin": row["periodo_produccion.fin_mes"]
        })

if not df_filtrado.empty:
    for _, row in df_filtrado.iterrows():
        if "entidades.coordenadas.lat" in row and pd.notna(row["entidades.coordenadas.lat"]):
            map_points.append({
                "lat": row["entidades.coordenadas.lat"],
                "lon": row["entidades.coordenadas.lon"],
                "tipo": "Noticia",
                "titulo": row["titulo"],
                "fuente": row["fuente"],
                "fecha": row["fecha_recogida"],
                "nivel": row.get("nivel", "N/A"),
                "razon": row.get("razon", "N/A")
            })

# Mostrar mapa
if map_points:
    df_map = pd.DataFrame(map_points)
    st.map(df_map, latitude="lat", longitude="lon")
    st.write("📍 Datos de puntos en el mapa:")
    st.dataframe(df_map)
else:
    st.warning("No se encontraron zonas o noticias con coordenadas para esta variedad.")

# ==== Gráfica de distribución temporal ====
if not df_filtrado.empty:
    st.write("### Distribución temporal de noticias")
    df_filtrado["fecha_recogida"] = pd.to_datetime(df_filtrado["fecha_recogida"])
    conteo = df_filtrado.groupby(df_filtrado["fecha_recogida"].dt.to_period("M")).size()
    st.bar_chart(conteo)
