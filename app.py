# app.py
import streamlit as st
import pandas as pd
import json
import re

# ==== Funciones auxiliares ====
@st.cache_data
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def split_variedades(variedad_raw):
    """Devuelve lista de variedades individuales a partir de strings como 'A / B'"""
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
            "fecha_recogida": n.get("fecha_recogida"),
            "fecha_noticia": n.get("fecha_noticia"),
            "fuente": n.get("fuente"),
            "url": n.get("url"),
            "titulo": n.get("titulo"),
            "resumen": n.get("resumen"),
            "categoria": n.get("categoria"),
            "idioma": n.get("idioma"),
            # entidad
            "entidades.pais": ent.get("pais"),
            "entidades.region": ent.get("region"),
            "entidades.producto": ent.get("producto"),
            "entidades.variedad": ent.get("variedad"),
            # coordenadas
            "lat": coords.get("lat"),
            "lon": coords.get("lon"),
            # campos adicionales
            "impacto_produccion": n.get("impacto_produccion"),
            "graduacion_sentimiento": n.get("graduacion_sentimiento"),
            "palabras_clave": n.get("palabras_clave"),
            "actores": n.get("actores"),
            "condiciones_mercado": n.get("condiciones_mercado"),
            "datos_produccion": n.get("datos_produccion"),
        }
        # Compatibilidad
        row["nivel"] = row["impacto_produccion"]
        row["razon"] = row["resumen"]
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
                "id_zona": z.get("id"),
                "fuente_zona": z.get("fuente"),
                "titulo_zona": z.get("titulo"),
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

# ==== Preparar productos y variedades ====
productos_variedades = {}

# De noticias
for _, row in df_noticias.iterrows():
    prod = row.get("entidades.producto")
    if not prod:
        continue
    if prod not in productos_variedades:
        productos_variedades[prod] = set()
    for v in row.get("variedades_list", []):
        productos_variedades[prod].add(v)

# De zonas
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

# ==== Sidebar ====
st.sidebar.title("Filtros")
producto_sel = st.sidebar.selectbox("Selecciona producto", ["Todos"] + sorted(productos_variedades.keys()))

if producto_sel == "Todos":
    variedad_sel = "Todas"
else:
    variedades = sorted(productos_variedades[producto_sel])
    variedad_sel = st.sidebar.selectbox("Selecciona variedad", ["Todas"] + variedades)

# ==== Filtrar noticias ====
if producto_sel == "Todos":
    df_filtrado = df_noticias.copy()
elif variedad_sel == "Todas":
    df_filtrado = df_noticias[df_noticias["entidades.producto"] == producto_sel]
else:
    df_filtrado = df_noticias[
        (df_noticias["entidades.producto"] == producto_sel) &
        (df_noticias["variedades_list"].apply(lambda L: variedad_sel in L))
    ]


# ==== Sidebar ====
st.sidebar.title("Filtros")
variedad_sel = st.sidebar.selectbox("Selecciona variedad (individual)", variedades_sorted)

# ==== Filtrar noticias ====
if variedad_sel == "Todas":
    df_filtrado = df_noticias.copy()
else:
    df_filtrado = df_noticias[df_noticias["variedades_list"].apply(lambda L: variedad_sel in L)]

st.title("📊 Cuadro de mandos agrícola — noticias ↔ zonas")
st.subheader(f"Variedad seleccionada: {variedad_sel}")

# ==== Tabla de noticias ====
cand_cols = [
    "fecha_recogida", "fecha_noticia", "fuente", "titulo",
    "entidades.pais", "entidades.region", "entidades.producto", "entidades.variedad",
    "nivel", "razon", "impacto_produccion", "resumen", "graduacion_sentimiento",
    "palabras_clave", "actores", "url", "categoria", "idioma"
]

if not df_filtrado.empty:
    df_show = df_filtrado.reindex(columns=cand_cols, fill_value="").copy()
    for col in ["palabras_clave", "actores"]:
        if col in df_show.columns:
            df_show[col] = df_show[col].apply(
                lambda x: ", ".join(map(str, x)) if isinstance(x, (list, tuple)) else (str(x) if x else "")
            )
    st.write("### Noticias relacionadas")
    st.dataframe(df_show.sort_values(by="fecha_recogida", ascending=False).reset_index(drop=True))
else:
    st.info("No hay noticias para esa variedad.")

# ==== Cruce con zonas ====
st.write("### Zonas de producción potencialmente afectadas")

producto = None
if not df_filtrado.empty and "entidades.producto" in df_filtrado.columns:
    productos = df_filtrado["entidades.producto"].dropna().unique()
    producto = productos[0] if len(productos) > 0 else None

if variedad_sel == "Todas":
    zonas_rel = df_zonas.copy()
else:
    zonas_rel = df_zonas[
        (df_zonas["entidades.variedad"].fillna("").str.contains(re.escape(variedad_sel))) |
        (df_zonas["entidades.producto"].fillna("").str.contains(re.escape(variedad_sel)))
    ]

if zonas_rel.empty and producto:
    zonas_rel = df_zonas[df_zonas["entidades.producto"].fillna("").str.contains(re.escape(producto))]

map_points = []
for _, z in zonas_rel.iterrows():
    try:
        lat = float(z["lat"]) if pd.notna(z["lat"]) else None
        lon = float(z["lon"]) if pd.notna(z["lon"]) else None
    except Exception:
        lat = lon = None
    if lat is None or lon is None:
        continue
    map_points.append({
        "lat": lat,
        "lon": lon,
        "tipo": "Zona",
        "etiqueta": f"{z.get('region','')} ({z.get('pais','')})",
        "producto": z.get("entidades.producto"),
        "variedad_meta": z.get("entidades.variedad"),
        "periodo_inicio": z.get("periodo_inicio"),
        "periodo_fin": z.get("periodo_fin"),
        "volumen_tn": z.get("volumen_estimado_tn")
    })

for _, n in df_filtrado.iterrows():
    try:
        lat = float(n["lat"]) if pd.notna(n["lat"]) else None
        lon = float(n["lon"]) if pd.notna(n["lon"]) else None
    except Exception:
        lat = lon = None
    if lat is None or lon is None:
        continue
    map_points.append({
        "lat": lat,
        "lon": lon,
        "tipo": "Noticia",
        "etiqueta": n.get("titulo") or n.get("resumen") or "",
        "fuente": n.get("fuente"),
        "fecha": n.get("fecha_recogida"),
        "nivel": n.get("nivel"),
        "razon": n.get("razon")
    })

if map_points:
    df_map = pd.DataFrame(map_points)
    st.map(df_map[["lat", "lon"]])
    st.write("📍 Puntos (zonas y noticias) — detalles:")
    st.dataframe(df_map)
else:
    st.warning("No se encontraron puntos con coordenadas para la selección actual.")

# ==== Gráfica temporal ====
st.write("### Evolución temporal de noticias")
if not df_filtrado.empty:
    df_dates = df_filtrado.copy()
    df_dates["fecha_parsed"] = pd.NaT
    for col in ["fecha_recogida", "fecha_noticia"]:
        if col in df_dates.columns:
            df_dates["fecha_parsed"] = pd.to_datetime(df_dates[col], errors="coerce").fillna(df_dates["fecha_parsed"])
    df_dates = df_dates.dropna(subset=["fecha_parsed"])
    if not df_dates.empty:
        counts = df_dates.groupby(df_dates["fecha_parsed"].dt.to_period("M")).size()
        counts.index = counts.index.to_timestamp()
        st.bar_chart(counts)
    else:
        st.info("No hay fechas válidas en las noticias para graficar.")
else:
    st.info("Selecciona una variedad con noticias para ver la evolución temporal.")
