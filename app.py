# app.py
import streamlit as st
import pandas as pd
import json
import re
import math
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import pydeck as pdk

# ------------------ Configuración ------------------
st.set_page_config(layout="wide", page_title="Dashboard Agrícola", page_icon="🌱")

# ------------------ Helpers ------------------
@st.cache_data
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def split_variedades(variedad_raw):
    if not variedad_raw or not isinstance(variedad_raw, str):
        return []
    parts = re.split(r'[\/,;|]+', variedad_raw)
    return [p.strip() for p in parts if p.strip()]

def months_set(start, end):
    """Devuelve conjunto de meses (1..12) incluidos entre start y end (soporta wrap-around)."""
    try:
        s = int(start)
        e = int(end)
    except Exception:
        return set()
    if s <= e:
        return set(range(s, e + 1))
    else:
        # wrap around year
        return set(list(range(s, 13)) + list(range(1, e + 1)))

# ------------------ Flatten JSONs ------------------
def flatten_noticias(noticias_raw):
    rows = []
    for n in noticias_raw:
        ent = n.get("entidades", {}) or {}
        coords = ent.get("coordenadas", {}) or {}
        row = {
            "id": n.get("id"),
            "fecha_noticia": n.get("fecha_noticia") or n.get("fecha_recogida"),
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

# ------------------ Cargar datos ------------------
noticias_raw = load_json("noticias.json")
zonas_raw = load_json("zonas.json")

df_noticias = flatten_noticias(noticias_raw)
df_zonas = flatten_zonas(zonas_raw)

# ------------------ Header (logos) ------------------
try:
    hcol1, hcol2, hcol3 = st.columns([1, 6, 1])
    with hcol1:
        st.image("img/logo.png", width=140)
    with hcol3:
        st.image("img/ucam.png", width=440)
    with hcol2:
        st.markdown("<h1 style='text-align:center;margin-top:18px;'>Sistema de alertas y prospección mediante redes sociales</h1>", unsafe_allow_html=True)
except Exception:
    # si falta alguna imagen no falla la app
    st.title("Cuadro de mandos: Noticias & Zonas de Producción")

# ------------------ Preparar productos y variedades ------------------
productos_variedades = {}

# desde noticias
for _, row in df_noticias.iterrows():
    prod = row.get("entidades.producto")
    if not prod:
        continue
    productos_variedades.setdefault(prod, set())
    for v in row.get("variedades_list", []):
        productos_variedades[prod].add(v)

# desde zonas
for _, row in df_zonas.iterrows():
    prod = row.get("entidades.producto")
    var = row.get("entidades.variedad")
    if not prod:
        continue
    productos_variedades.setdefault(prod, set())
    if isinstance(var, str):
        for v in re.split(r'[\/,;|]+', var):
            v = v.strip()
            if v:
                productos_variedades[prod].add(v)

# ------------------ Sidebar filtros ------------------
st.sidebar.title("Filtros")
producto_sel = st.sidebar.selectbox("Selecciona producto", ["Todos"] + sorted(productos_variedades.keys()))

if producto_sel == "Todos":
    variedad_sel = "Todas"
else:
    variedades = sorted(productos_variedades.get(producto_sel, []))
    variedad_sel = st.sidebar.selectbox("Selecciona variedad (opcional)", ["Todas"] + variedades)

mes_desde = st.sidebar.slider("Mes desde", 1, 12, 1)
mes_hasta = st.sidebar.slider("Mes hasta", 1, 12, 12)

# ------------------ Filtrado noticias ------------------
df_filtrado = df_noticias.copy()

if producto_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["entidades.producto"] == producto_sel]

if variedad_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado["variedades_list"].apply(lambda L: variedad_sel in L)]

# parsear fecha de noticia y filtrar por meses (soporta wrap-around)
df_filtrado["fecha_parsed"] = pd.to_datetime(df_filtrado["fecha_noticia"], errors="coerce")
allowed_months = months_set(mes_desde, mes_hasta)
df_filtrado = df_filtrado[df_filtrado["fecha_parsed"].dt.month.isin(allowed_months)]

# ------------------ Filtrado zonas por producto/variedad y meses (overlap) ------------------
df_zonas_filtrado = df_zonas.copy()
if producto_sel != "Todos":
    df_zonas_filtrado = df_zonas_filtrado[df_zonas_filtrado["entidades.producto"] == producto_sel]
if variedad_sel != "Todas":
    df_zonas_filtrado = df_zonas_filtrado[df_zonas_filtrado["entidades.variedad"].fillna("").str.contains(re.escape(variedad_sel))]

# comprobar solapamiento de meses
def zona_overlap(row):
    try:
        s = int(row.get("periodo_inicio"))
        e = int(row.get("periodo_fin"))
    except Exception:
        return False
    return len(months_set(s, e).intersection(allowed_months)) > 0

if not df_zonas_filtrado.empty:
    df_zonas_filtrado = df_zonas_filtrado[df_zonas_filtrado.apply(zona_overlap, axis=1)]

# ------------------ Interfaz principal ------------------
st.markdown("## Resultados")
st.write(f"**Producto:** {producto_sel}   ·   **Variedad:** {variedad_sel}   ·   **Meses:** {mes_desde} → {mes_hasta}")

# ------------------ Tabla de noticias (fila coloreada por sentimiento) ------------------
st.markdown("### 📰 Noticias filtradas")
if not df_filtrado.empty:
    cols_to_show = ["fecha_noticia", "fuente", "titulo", "entidades.pais", "entidades.region",
                    "entidades.producto", "entidades.variedad", "graduacion_sentimiento"]
    df_show = df_filtrado[cols_to_show].copy().fillna("")

    def row_style(row):
        v = row.get("graduacion_sentimiento")
        try:
            val = float(v)
        except Exception:
            val = None
        if val is None:
            color = ""
        elif val > 0.2:
            color = "background-color: rgba(0,200,0,0.12)"
        elif val < -0.2:
            color = "background-color: rgba(200,0,0,0.12)"
        else:
            color = "background-color: rgba(200,200,200,0.12)"
        return [color] * len(row)

    styled = df_show.style.apply(row_style, axis=1)
    st.dataframe(styled, use_container_width=True)
else:
    st.info("No hay noticias para la selección actual.")

# ------------------ Nube de palabras única ------------------
st.markdown("### ☁️ Nube de palabras (palabras clave + actores)")
if not df_filtrado.empty:
    palabras = []
    for _, row in df_filtrado.iterrows():
        pk = row.get("palabras_clave")
        ac = row.get("actores")
        if isinstance(pk, (list, tuple)):
            palabras.extend([str(x) for x in pk if x])
        if isinstance(ac, (list, tuple)):
            palabras.extend([str(x) for x in ac if x])
    if palabras:
        wc = WordCloud(width=1000, height=380, background_color="white", colormap="viridis").generate(" ".join(palabras))
        fig, ax = plt.subplots(figsize=(10,4))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.info("No hay palabras clave/actores disponibles para generar la nube.")
else:
    st.info("No hay datos para generar la nube.")

# ------------------ Preparar datos para el mapa (con nombres sencillos para tooltip) ------------------
# Zonas
zones_for_map = []
if not df_zonas_filtrado.empty:
    zdf = df_zonas_filtrado.dropna(subset=["lat", "lon"]).copy()
    if not zdf.empty:
        # normalizar radios: usar escala sqrt para que no se hagan gigantes
        max_vol = zdf["volumen_estimado_tn"].max() or 1
        # radius = sqrt(volume/max_vol) * base_scale
        base_scale = 200000  # ajustable
        zdf["radius"] = (zdf["volumen_estimado_tn"].apply(lambda v: math.sqrt(max(v, 0)))) / math.sqrt(max_vol) * base_scale + 20000
        for _, r in zdf.iterrows():
            zones_for_map.append({
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "type": "Zona",
                "title": "",
                "product": r.get("entidades.producto", ""),
                "variety": r.get("entidades.variedad", ""),
                "region": r.get("region", ""),
                "country": r.get("pais", ""),
                "volume": int(r.get("volumen_estimado_tn")) if pd.notna(r.get("volumen_estimado_tn")) else "",
                "source": "",
                "date": f"{int(r.get('periodo_inicio')) if pd.notna(r.get('periodo_inicio')) else ''}-{int(r.get('periodo_fin')) if pd.notna(r.get('periodo_fin')) else ''}",
                "sentiment": "",
                "radius": float(r["radius"])
            })

# Noticias
news_for_map = []
if not df_filtrado.empty:
    ndf = df_filtrado.dropna(subset=["lat", "lon"]).copy()
    if not ndf.empty:
        # radius fixed but modest
        news_radius = 30000
        for _, r in ndf.iterrows():
            date_str = ""
            if pd.notna(r.get("fecha_parsed")):
                date_str = r["fecha_parsed"].strftime("%Y-%m-%d")
            news_for_map.append({
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "type": "Noticia",
                "title": r.get("titulo", ""),
                "product": r.get("entidades.producto", ""),
                "variety": (r.get("variedades_list") and ", ".join(r.get("variedades_list"))) or r.get("entidades.variedad", ""),
                "region": r.get("entidades.region", ""),
                "country": r.get("entidades.pais", ""),
                "volume": "",
                "source": r.get("fuente", ""),
                "date": date_str,
                "sentiment": (str(r.get("graduacion_sentimiento")) if pd.notna(r.get("graduacion_sentimiento")) else ""),
                "radius": news_radius
            })

# ------------------ Mapa: capas y tooltip ------------------
st.markdown("### 🗺️ Zonas de producción y noticias")

map_data_z = pd.DataFrame(zones_for_map) if zones_for_map else pd.DataFrame(columns=[
    "lat","lon","type","title","product","variety","region","country","volume","source","date","sentiment","radius"
])
map_data_n = pd.DataFrame(news_for_map) if news_for_map else pd.DataFrame(columns=map_data_z.columns)

layers = []
all_points = []

if not map_data_z.empty:
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=map_data_z,
            get_position=["lon","lat"],
            get_radius="radius",
            radius_scale=1,
            get_fill_color=[0, 128, 0, 160],
            pickable=True,
        )
    )
    all_points.extend(map_data_z[["lat","lon"]].values.tolist())

if not map_data_n.empty:
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=map_data_n,
            get_position=["lon","lat"],
            get_radius="radius",
            radius_scale=1,
            get_fill_color=[200, 0, 0, 160],
            pickable=True,
        )
    )
    all_points.extend(map_data_n[["lat","lon"]].values.tolist())

if layers and all_points:
    lats, lons = zip(*all_points)
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    # heurística de zoom basada en la extensión máxima
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    span = max(abs(lat_max - lat_min), abs(lon_max - lon_min))
    if span < 0.5:
        zoom = 8
    elif span < 2:
        zoom = 7
    elif span < 5:
        zoom = 6
    elif span < 10:
        zoom = 5
    elif span < 30:
        zoom = 4
    else:
        zoom = 2

    view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=zoom, pitch=0)

    tooltip = {
        "html": (
            "<b>{type}</b><br/>"
            "<b>Título:</b> {title}<br/>"
            "<b>Producto:</b> {product}  <b>Variedad:</b> {variety}<br/>"
            "<b>Región:</b> {region}, {country}<br/>"
            "<b>Volumen (tn):</b> {volume}<br/>"
            "<b>Fuente:</b> {source}<br/>"
            "<b>Fecha:</b> {date}<br/>"
            "<b>Sentimiento:</b> {sentiment}"
        ),
        "style": {"backgroundColor": "white", "color": "black"}
    }

    deck = pdk.Deck(layers=layers, initial_view_state=view_state, map_style="light", tooltip=tooltip)
    st.pydeck_chart(deck, use_container_width=True)
else:
    st.info("No hay datos geográficos que mostrar para los filtros actuales.")

# ------------------ Footer (logos) ------------------
st.markdown("---")
try:
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        st.image("img/murcia.png", width=200)
    with fcol2:
        st.image("img/logos-gob.jpg", width=550)
except Exception:
    st.markdown("Logos de pie no disponibles (falta la carpeta `img/` o las imágenes).")
