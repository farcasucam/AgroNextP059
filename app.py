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
