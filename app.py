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

st.set_page_config(page_title="Subida CSV/XLSX → corven.crudo_ap", layout="centered")

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
    </style>
""", unsafe_allow_html=True)

# ---- Header ----
if logo_b64:
    st.markdown(f"""
    <div class="header-container">
        <div class="header-title">Subida de CSV/XLSX → <strong>corven.crudo_ap</strong></div>
        <div class="header-logo"><img src="data:image/png;base64,{logo_b64}" /></div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="header-container">
        <div class="header-title">Subida de CSV/XLSX → <strong>corven.crudo_ap</strong></div>
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

    # Renombrar columnas: a, b, c, ..., n, ...
    df.columns = gen_colnames(df.shape[1])

    # Vista previa
    st.write("Vista previa del archivo:")
    st.dataframe(df.head(100), use_container_width=True)

    # Métricas inmediatas: filas y suma(columna 'n')
    total_filas = len(df)
    if 'n' in df.columns:
        suma_n = pd.to_numeric(df['n'], errors='coerce').sum()
        st.markdown(
            f"<div style='color:#64352c; font-weight:bold; margin:10px 0;'>"
            f"Filas detectadas: <strong>{total_filas}</strong> &nbsp;|&nbsp; "
            f"Suma de <strong>n</strong>: <strong>{suma_n:.2f}</strong>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.error("No se encontró la columna **n** en el archivo. Revisá que el archivo tenga al menos 14 columnas (… m, **n**, o…).")

    # Confirmación
    if st.button("Subir y Actualizar Repositorio", type="primary"):
        try:
            if df.empty:
                st.warning("El archivo no tiene filas.")
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
                conn.commit()

                # Contar filas cargadas
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
