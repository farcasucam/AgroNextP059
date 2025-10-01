import streamlit as st
import pandas as pd
import json
import re
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import pydeck as pdk

# ==== Configuración general ====
st.set_page_config(layout="wide")

# ==== Funciones auxiliares ====
@st.cache_data
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def split_variedades(variedad_raw):
    if not variedad_raw or not isinstance(variedad_raw, str):
        return []
    parts = re.split(r'[\/,;|]+', variedad_raw)
    return [p.strip() for p in parts if p.strip()]

def flatten_noticias(noticias_raw):
    rows = []
    for n in noticias_raw:
        ent = n.get("entidades", {}) or {}
        coords = ent.get("coordenadas", {}) or {}
        row = {
            "id": n.get("id"),
            "fecha_noticia": n.get("fecha_noticia"),
            "fuente": n.get("fuente"),
            "titulo": n.get("titulo"),
            "resumen": n.get("resumen"),
            "categoria": n.get("categoria"),
            "idioma": n.get("idioma"),
            "entidades.pais": ent.get("pais"),
            "entidades.region": ent.get("region"),
            "entidades.producto": ent.get("producto"),
            "entidades.variedad": ent.get("variedad"),
            "lat": coords.get("lat"),
            "lon": coords.get("lon"),
            "graduacion_sentimiento": n.get("graduacion_sentimiento"),
            "palabras_clave": n.get("palabras_clave"),
            "actores": n.get("actores"),
        }
        row["variedades_list"] = split_variedades(row["entidades.variedad"])
        rows.append(row)
    return pd.DataFrame(rows)

def flatten_zonas(zonas_raw):
    rows = []
    for z in zonas_raw:
        ent = z.get("entidades", {}) or {}
        prod = ent.get("producto")
        variedad_ent = ent.get("variedad")
        for zp in ent.get("zonas_produccion", []) or []:
            coords = zp.get("coordenadas", {}) or {}
            periodo = zp.get("periodo_produccion", {}) or {}
            rows.append({
                "entidades.producto": prod,
                "entidades.variedad": variedad_ent,
                "pais": zp.get("pais"),
                "region": zp.get("region"),
                "lat": coords.get("lat"),
                "lon": coords.get("lon"),
                "periodo_inicio": periodo.get("inicio_mes"),
                "periodo_fin": periodo.get("fin_mes"),
                "volumen_estimado_tn": zp.get("volumen_estimado_tn"),
            })
    return pd.DataFrame(rows)

# ==== Carga datos ====
noticias_raw = load_json("noticias.json")
zonas_raw = load_json("zonas.json")

df_noticias = flatten_noticias(noticias_raw)
df_zonas = flatten_zonas(zonas_raw)

# ==== Sidebar filtros ====
# Productos y variedades
productos_variedades = {}
for _, row in df_noticias.iterrows():
    prod = row.get("entidades.producto")
    if not prod:
        continue
    if prod not in productos_variedades:
        productos_variedades[prod] = set()
    for v in row.get("variedades_list", []):
        productos_variedades[prod].add(v)

for _, row in df_zonas.iterrows():
    prod = row.get("entidades.producto")
    var = row.get("entidades.variedad")
    if not prod:
        continue
    if prod not in productos_variedades:
        productos_variedades[prod] = set()
    if isinstance(var, str):
        for v in re.split(r'[\/,;|]+', var):
            v = v.strip()
            if v:
                productos_variedades[prod].add(v)

st.sidebar.title("Filtros")
producto_sel = st.sidebar.selectbox("Selecciona producto", ["Todos"] + sorted(productos_variedades.keys()))

if producto_sel == "Todos":
    variedad_sel = "Todas"
else:
    variedades = sorted(productos_variedades[producto_sel])
    variedad_sel = st.sidebar.selectbox("Selecciona variedad", ["Todas"] + variedades)

# Filtro por mes
mes_desde = st.sidebar.slider("Mes desde", 1, 12, 1)
mes_hasta = st.sidebar.slider("Mes hasta", 1, 12, 12)

# ==== Filtrar noticias ====
df_filtrado = df_noticias.copy()
if producto_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["entidades.producto"] == producto_sel]
if variedad_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado["variedades_list"].apply(lambda L: variedad_sel in L)]

# Filtro por mes en noticias
df_filtrado["fecha_parsed"] = pd.to_datetime(df_filtrado["fecha_noticia"], errors="coerce")
df_filtrado = df_filtrado[df_filtrado["fecha_parsed"].dt.month.between(mes_desde, mes_hasta, inclusive="both")]

# ==== Filtrar zonas ====
df_zonas_filtrado = df_zonas.copy()
if producto_sel != "Todos":
    df_zonas_filtrado = df_zonas_filtrado[df_zonas_filtrado["entidades.producto"] == producto_sel]
if variedad_sel != "Todas":
    df_zonas_filtrado = df_zonas_filtrado[df_zonas_filtrado["entidades.variedad"].fillna("").str.contains(variedad_sel)]

# Filtro por periodo de producción y meses seleccionados
df_zonas_filtrado = df_zonas_filtrado[
    (df_zonas_filtrado["periodo_inicio"] <= mes_hasta) &
    (df_zonas_filtrado["periodo_fin"] >= mes_desde)
]

# ==== Layout principal ====
st.title("📊 Cuadro de mandos agrícola — noticias y zonas de producción")

# ---- Noticias en tabla con color por sentimiento ----
if not df_filtrado.empty:
    st.subheader("📰 Noticias filtradas")

    cols_to_show = ["fecha_noticia", "fuente", "titulo", "entidades.pais", "entidades.region",
                    "entidades.producto", "entidades.variedad", "graduacion_sentimiento"]

    df_show = df_filtrado[cols_to_show].copy().fillna("")

    def sentiment_color(val):
        if pd.isna(val):
            return ""
        try:
            v = float(val)
            if v > 0.2:
                return "background-color: rgba(0,200,0,0.2)"  # verde
            elif v < -0.2:
                return "background-color: rgba(200,0,0,0.2)"  # rojo
            else:
                return "background-color: rgba(200,200,200,0.2)"  # gris
        except:
            return ""

    st.dataframe(
        df_show.style.applymap(sentiment_color, subset=["graduacion_sentimiento"]),
        use_container_width=True
    )
else:
    st.info("No hay noticias para la selección actual.")

# ---- Nube de palabras ----
if not df_filtrado.empty:
    st.subheader("☁️ Nubes de palabras")
    palabras = []
    actores = []
    for _, row in df_filtrado.iterrows():
        if isinstance(row["palabras_clave"], list):
            palabras.extend(row["palabras_clave"])
        if isinstance(row["actores"], list):
            actores.extend(row["actores"])

    col1, col2 = st.columns(2)
    if palabras:
        wc = WordCloud(width=400, height=300, background_color="white").generate(" ".join(palabras))
        fig, ax = plt.subplots(figsize=(5,4))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        col1.pyplot(fig)
    if actores:
        wc2 = WordCloud(width=400, height=300, background_color="white", colormap="plasma").generate(" ".join(actores))
        fig2, ax2 = plt.subplots(figsize=(5,4))
        ax2.imshow(wc2, interpolation="bilinear")
        ax2.axis("off")
        col2.pyplot(fig2)

# ---- Mapa ----
st.subheader("🗺️ Zonas de producción y noticias")

map_layers = []

# Zonas de producción (círculos escalados por volumen)
if not df_zonas_filtrado.empty:
    df_zonas_filtrado = df_zonas_filtrado.dropna(subset=["lat", "lon", "volumen_estimado_tn"])
    if not df_zonas_filtrado.empty:
        zonas_layer = pdk.Layer(
            "ScatterplotLayer",
            data=df_zonas_filtrado,
            get_position=["lon","lat"],
            get_radius="volumen_estimado_tn",
            radius_scale=1,
            get_fill_color=[0, 128, 0, 140],
            pickable=True,
        )
        map_layers.append(zonas_layer)

# Noticias (puntos rojos)
if not df_filtrado.empty:
    df_news_map = df_filtrado.dropna(subset=["lat", "lon"])
    if not df_news_map.empty:
        news_layer = pdk.Layer(
            "ScatterplotLayer",
            data=df_news_map,
            get_position=["lon","lat"],
            get_radius=50000,
            get_fill_color=[200, 0, 0, 160],
            pickable=True,
        )
        map_layers.append(news_layer)

if map_layers:
    view_state = pdk.ViewState(latitude=20, longitude=0, zoom=1.5)
    st.pydeck_chart(pdk.Deck(layers=map_layers, initial_view_state=view_state))
else:
    st.info("No hay datos geográficos para mostrar.")

# ---- Footer con logos ----
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center;">
        <a href="https://www.agroalnext.es/" target="_blank">
            <img src="https://www.agroalnext.es/wp-content/uploads/2023/06/Agroalnext-Logo.png" 
                 alt="Agroalnext" height="80">
        </a>
    </div>
    """,
    unsafe_allow_html=True
)
