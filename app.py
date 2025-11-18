# app.py
import streamlit as st
import pandas as pd
import mysql.connector
from mysql.connector import ClientFlag
import tempfile
import os
from PIL import Image
import base64
import io
import string

st.set_page_config(page_title="Input FBL1N", layout="centered")

# ---- Logo a base64 (opcional) ----
def get_base64_logo(path="logorelleno.png"):
    try:
        img = Image.open(path).resize((40, 40))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return None

logo_b64 = get_base64_logo()

# ---- Estilos ----
st.markdown("""
    <style>
    .main { background-color: #d4fdb7 !important; }
    .main > div:first-child { padding-top: 0rem; }
    .header-container {
        display:flex; justify-content:space-between; align-items:center;
        padding:2px 0 10px 0; border-bottom:2px solid #d4fdb7; margin-bottom:20px;
    }
    .header-title {
        font-size:24px; font-weight:bold; color:#d4fdb7;
        text-shadow:-1px -1px 0 #64352c, 1px -1px 0 #64352c, -1px 1px 0 #64352c, 1px 1px 0 #64352c;
    }
    .header-logo img { height:40px; }
    button[kind="primary"] { background-color:#64352c !important; border-color:#64352c !important; color:white !important; }
    button[kind="primary"]:hover { background-color:#4f2923 !important; border-color:#4f2923 !important; }
    .stAlert[data-baseweb="alert"] { background-color:#f6fff0; color:#64352c !important; font-weight:bold; }
    label, .stSelectbox label, .stFileUploader label { color:#64352c !important; }

    .btn-red-info {
        background-color:#b91c1c;
        color:white;
        border:none;
        padding:0.5rem 1rem;
        border-radius:0.25rem;
        font-weight:bold;
        cursor:default;
    }
    .btn-red-info:disabled {
        opacity:0.9;
    }
    </style>
""", unsafe_allow_html=True)

# ---- Header ----
if logo_b64:
    st.markdown(f"""
    <div class="header-container">
        <div class="header-title">Input FBL1N</div>
        <div class="header-logo"><img src="data:image/png;base64,{logo_b64}" /></div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="header-container">
        <div class="header-title">Input FBL1N</div>
    </div>
    """, unsafe_allow_html=True)


# -------------------- Helpers --------------------
def open_connection():
    return mysql.connector.connect(
        host=st.secrets["DB_HOST"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_NAME"],
        charset="utf8mb4",
        use_unicode=True,
        allow_local_infile=True,
        client_flags=[ClientFlag.LOCAL_FILES]
    )

def gen_colnames(n_cols: int):
    """
    Genera nombres tipo a, b, c, ..., z, aa, ab, ... en minúscula.
    """
    names = []
    alphabet = string.ascii_lowercase
    base = len(alphabet)
    for i in range(n_cols):
        s = ""
        x = i
        while True:
            s = alphabet[x % base] + s
            x = x // base - 1
            if x < 0:
                break
        names.append(s)
    return names

# -------------------- LÓGICA PRINCIPAL --------------------
uploaded_file = st.file_uploader("Subí tu archivo CSV o XLSX (sin encabezados)", type=["csv", "xlsx"])

if uploaded_file:
    # Leer SIN encabezados
    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file, header=None)
    else:
        # para xlsx sin encabezados
        df = pd.read_excel(uploaded_file, header=None)  # requiere openpyxl

    # Renombrar columnas: a, b, c, ..., o, ...
    df.columns = gen_colnames(df.shape[1])

    # -------------------- FILTRAR FILAS SIN SOCIEDAD (columna 'a') --------------------
    total_filas_original = len(df)

    # Nos quedamos solo con filas donde 'a' tenga algún valor no vacío
    df = df[df['a'].notna() & (df['a'].astype(str).str.strip() != "")]
    df.reset_index(drop=True, inplace=True)

    total_filas = len(df)
    filtradas = total_filas_original - total_filas

    if filtradas > 0:
        st.warning(f"Se eliminaron {filtradas} filas sin Sociedad en la primera columna (columna 'a').")

    if df.empty:
        st.error("Luego de eliminar filas sin Sociedad, el archivo quedó vacío. Revisá el archivo de origen.")
    else:
        # Vista previa
        st.write("Vista previa del archivo (ya filtrado sin filas sin Sociedad):")
        st.dataframe(df.head(100), use_container_width=True)

        # Métricas inmediatas: filas y suma(columna 'o')
        if 'o' in df.columns:
            suma_o = pd.to_numeric(df['o'], errors='coerce').sum()
            st.markdown(
                f"<div style='color:#64352c; font-weight:bold; margin:10px 0;'>"
                f"Filas válidas (con Sociedad): <strong>{total_filas}</strong> &nbsp;|&nbsp; "
                f"Suma de <strong>o</strong>: <strong>{suma_o:.2f}</strong>"
                f"</div>",
                unsafe_allow_html=True
            )
        else:
            st.error(
                "No se encontró la columna **o** en el archivo. "
                "Revisá que el archivo tenga al menos 15 columnas (… n, **o**, …)."
            )

        # Confirmación
        if st.button("Subir y Actualizar Repositorio", type="primary"):
            try:
                if df.empty:
                    st.warning("El archivo no tiene filas válidas para cargar (todas fueron filtradas).")
                else:
                    # Guardar CSV temporal sin encabezados (importa por posición)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8", newline="\n") as tmp:
                        df.to_csv(tmp.name, index=False, header=False)
                        temp_path = tmp.name

                    # Conectar a MySQL
                    conn = open_connection()
                    cur = conn.cursor()

                    # 1) TRUNCATE
                    cur.execute("TRUNCATE TABLE `corven`.`crudo_ap`;")

                    # 2) LOAD DATA LOCAL INFILE (sin IGNORE 1 ROWS, porque no hay encabezados)
                    csv_path = temp_path.replace("\\", "\\\\")  # por si Windows
                    load_sql = f"""
                    LOAD DATA LOCAL INFILE '{csv_path}'
                    INTO TABLE `corven`.`crudo_ap`
                    CHARACTER SET utf8mb4
                    FIELDS TERMINATED BY ',' ENCLOSED BY '"' ESCAPED BY '"'
                    LINES TERMINATED BY '\\n';
                    """
                    cur.execute(load_sql)

                    # 3) Contar filas con FechaDoc inconsistente (0000-00-00) ANTES del delete
                    cur.execute("SELECT COUNT(*) FROM `corven`.`crudo_ap` WHERE `FechaDoc` = '0000-00-00';")
                    retenidas = cur.fetchone()[0]

                    # 4) Limpieza post-carga
                    cur.execute("DELETE FROM `corven`.`crudo_ap` WHERE `FechaDoc` = '0000-00-00';")

                    conn.commit()

                    # Guardar el número de filas retenidas en session_state para mostrarlo en el botón rojo
                    st.session_state["filas_inconsistentes"] = retenidas

                    # Contar filas cargadas finales
                    cur.execute("SELECT COUNT(*) FROM `corven`.`crudo_ap`;")
                    total = cur.fetchone()[0]

                    cur.close()
                    conn.close()

                    # Limpiar archivo temporal
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

                    st.success(f"Carga completada. Filas actuales en `corven`.`crudo_ap`: {total}.")

            except Exception as e:
                st.error(f"Error durante la carga: {e}")

    # Botón rojo informativo debajo del botón verde
    if "filas_inconsistentes" in st.session_state:
        st.markdown(
            f"""
            <div style="margin-top:10px;">
                <button class="btn-red-info" disabled>
                    Filas retenidas por información inconsistente: {st.session_state["filas_inconsistentes"]}
                </button>
            </div>
            """,
            unsafe_allow_html=True
        )
