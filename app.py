# app.py
import streamlit as st
import pandas as pd
import json
import re

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
            # coordenadas (intentar varias rutas)
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
        # Compatibilidad: crear alias 'nivel' y 'razon' si código espera esos campos
        row["nivel"] = row["impacto_produccion"]
        row["razon"] = row["resumen"]
        # lista de variedades individuales
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

# ---- Carga datos ----
noticias_raw = load_json("noticias.json")
zonas_raw = load_json("zonas.json")

df_noticias = flatten_noticias(noticias_raw)
df_zonas = flatten_zonas(zonas_raw)

# Generar lista de variedades únicas (explosión)
all_variedades = set()
for lst in df_noticias["variedades_list"].fillna([]):
    for v in lst:
        all_variedades.add(v)
# Añadir también las variedades que vienen en zonas.json (meta)
for v in df_zonas["entidades.variedad"].fillna(""):
    if isinstance(v, str):
        for s in re.split(r'[\/,;|]+', v):
            s = s.strip()
            if s:
                all_variedades.add(s)

variedades_sorted = sorted([v for v in all_variedades if v])
variedades_sorted.insert(0, "Todas")  # opción para ver todo

st.sidebar.title("Filtros")
variedad_sel = st.sidebar.selectbox("Selecciona variedad (individual)", variedades_sorted)

# Filtrado de noticias por variedad seleccionada
if variedad_sel == "Todas":
    df_filtrado = df_noticias.copy()
else:
    # Filtrar por lista de variedades
    df_filtrado = df_noticias[df_noticias["variedades_list"].apply(lambda L: variedad_sel in L)]

st.title("📊 Cuadro de mandos agrícola — noticias ↔ zonas")
st.subheader(f"Variedad seleccionada: {variedad_sel}")

# Tabla de noticias (selección segura de columnas)
cand_cols = [
    "fecha_recogida", "fecha_noticia", "fuente", "titulo",
    "entidades.pais", "entidades.region", "entidades.producto", "entidades.variedad",
    "nivel", "razon", "impacto_produccion", "resumen", "graduacion_sentimiento",
    "palabras_clave", "actores", "url", "categoria", "idioma"
]
display_cols = [c for c in cand_cols if c in df_filtrado.columns]
if not df_filtrado.empty:
    # Formatear columnas complejas para visualización
    df_show = df_filtrado[display_cols].copy()
    # Convertir listas a string para la tabla
    for col in ["palabras_clave", "actores"]:
        if col in df_show.columns:
            df_show[col] = df_show[col].apply(lambda x: ", ".join(x) if isinstance(x, (list, tuple)) else x)
    st.write("### Noticias relacionadas")
    st.dataframe(df_show.sort_values(by="fecha_recogida", ascending=False).reset_index(drop=True))
else:
    st.info("No hay noticias para esa variedad.")

# ---- Cruce con zonas de producción ----
st.write("### Zonas de producción potencialmente afectadas")

# Buscar zonas que correspondan a la variedad o al producto
# Para producto, tomaremos el primer producto de las noticias filtradas (si existe)
producto = None
if not df_filtrado.empty and "entidades.producto" in df_filtrado.columns:
    producto = df_filtrado["entidades.producto"].dropna().unique()
    producto = producto[0] if len(producto) > 0 else None

# Zonas que tengan la variedad explícita o el mismo producto
if variedad_sel == "Todas":
    zonas_rel = df_zonas.copy()
else:
    zonas_rel = df_zonas[
        (df_zonas["entidades.variedad"].fillna("").str.contains(re.escape(variedad_sel))) |
        (df_zonas["entidades.producto"].fillna("").str.contains(re.escape(variedad_sel)))
    ]

# Si no encontramos por variedad, intentar por producto
if zonas_rel.empty and producto:
    zonas_rel = df_zonas[df_zonas["entidades.producto"].fillna("").str.contains(re.escape(producto))]

# Preparamos puntos para el mapa (zonas + noticias)
map_points = []
# Zonas
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

# Noticias
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
    # st.map espera columnas lat/lon o latitude/longitude (se aceptan lat/lon)
    st.map(df_map.rename(columns={"lat": "lat", "lon": "lon"})[["lat", "lon"]])
    st.write("📍 Puntos (zonas y noticias) — detalles:")
    st.dataframe(df_map)
else:
    st.warning("No se encontraron puntos con coordenadas (zonas o noticias) para la selección actual.")

# ---- Gráfica temporal (noticias por mes) ----
st.write("### Evolución temporal de noticias")
if not df_filtrado.empty:
    df_dates = df_filtrado.copy()
    # Intentar parsear fechas desde fecha_recogida / fecha_noticia
    if "fecha_recogida" in df_dates.columns:
        df_dates["fecha_parsed"] = pd.to_datetime(df_dates["fecha_recogida"], errors="coerce")
    elif "fecha_noticia" in df_dates.columns:
        df_dates["fecha_parsed"] = pd.to_datetime(df_dates["fecha_noticia"], errors="coerce")
    else:
        df_dates["fecha_parsed"] = pd.NaT
    df_dates = df_dates.dropna(subset=["fecha_parsed"])
    if not df_dates.empty:
        counts = df_dates.groupby(df_dates["fecha_parsed"].dt.to_period("M")).size()
        # convertir a serie con índice datetime para st.bar_chart
        counts.index = counts.index.to_timestamp()
        st.bar_chart(counts)
    else:
        st.info("No hay fechas válidas en las noticias para graficar.")
else:
    st.info("Selecciona una variedad con noticias para ver la evolución temporal.")
