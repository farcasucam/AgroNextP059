import streamlit as st
import pandas as pd
import json
import folium
from streamlit_folium import st_folium

# ==== Cargar datos ====
with open("noticias.json", "r", encoding="utf-8") as f:
    noticias = json.load(f)

with open("zonas.json", "r", encoding="utf-8") as f:
    zonas = json.load(f)

# Normalizar noticias y zonas en DataFrames
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
st.write("### Zonas de producción afectadas")

producto = df_filtrado["entidades.producto"].iloc[0] if not df_filtrado.empty else None
zonas_rel = df_zonas[
    (df_zonas["entidades.variedad"] == variedad_sel) |
    (df_zonas["entidades.producto"] == producto)
]

if not zonas_rel.empty:
    mapa = folium.Map(location=[20, 0], zoom_start=2)

    # Marcadores de zonas
    for _, row in zonas_rel.iterrows():
        inicio = row["periodo_produccion.inicio_mes"]
        fin = row["periodo_produccion.fin_mes"]
        popup = f"""
        <b>{row['entidades.producto']} ({row['entidades.variedad']})</b><br>
        {row['region']} - {row['pais']}<br>
        Periodo: {inicio} - {fin}<br>
        Producción estimada: {row['volumen_estimado_tn']:,} t
        """
        folium.Marker(
            location=[row["coordenadas.lat"], row["coordenadas.lon"]],
            popup=popup,
            icon=folium.Icon(color="green", icon="leaf")
        ).add_to(mapa)

    # Marcadores de noticias
    for _, row in df_filtrado.iterrows():
        if "entidades.coordenadas.lat" in row and pd.notna(row["entidades.coordenadas.lat"]):
            popup = f"""
            <b>Noticia:</b> {row['titulo']}<br>
            Nivel: {row.get('nivel', 'N/A')}<br>
            Razón: {row.get('razon', 'N/A')}<br>
            Fecha: {row['fecha_recogida']}<br>
            Fuente: {row['fuente']}
            """
            folium.Marker(
                location=[row["entidades.coordenadas.lat"], row["entidades.coordenadas.lon"]],
                popup=popup,
                icon=folium.Icon(color="red", icon="info-sign")
            ).add_to(mapa)

    st_folium(mapa, width=900, height=500)
else:
    st.warning("No se encontraron zonas de producción relacionadas con esta variedad.")

# ==== Gráfica de distribución temporal ====
if not df_filtrado.empty:
    st.write("### Distribución temporal de noticias")
    df_filtrado["fecha_recogida"] = pd.to_datetime(df_filtrado["fecha_recogida"])
    conteo = df_filtrado.groupby(df_filtrado["fecha_recogida"].dt.to_period("M")).size()
    st.bar_chart(conteo)
