from __future__ import annotations

from datetime import date
from io import BytesIO
import traceback

import pandas as pd
import streamlit as st

from ranking_core import (
    DEFAULT_EXCLUDED_PRODUCTS,
    DEFAULT_RANKING_DATE,
    REQUIRED_ANULACIONES_COLUMNS,
    REQUIRED_BAJAS_SALUD_COLUMNS,
    REQUIRED_FACTURACION_COLUMNS,
    REQUIRED_FACTURACION_ASESOR_COLUMNS,
    REQUIRED_FACTURACION_SALUD_COLUMNS,
    REQUIRED_FACTURACION_VIDA_COLUMNS,
    REQUIRED_MAPEO_COLUMNS,
    REQUIRED_PRIMAS_COLUMNS,
    REQUIRED_SINIESTROS_COLUMNS,
    add_mapeo_to_ranking,
    add_mapeo_to_simple_ranking,
    build_ranking_decesos_top10,
    build_ranking_asesor_decesos_top10,
    build_ranking_salud_top10,
    build_ranking_vida_top10,
    build_sheet_summary,
    calculate_facturacion_salud,
    calculate_facturacion_vida,
    calculate_ranking,
    calculate_ranking_asesor_decesos,
    dataframe_to_excel,
    format_euro,
    format_percent,
    prepare_mapeo_data,
    read_excel_all_sheets,
    read_excel_many_files,
    validate_columns,
)

st.set_page_config(page_title="Ranking agentes", page_icon="📊", layout="wide")

FILE_HELP = {
    "facturacion": "FACTURACION_DECESOS",
    "facturacion_asesor": "FACTURACION_DECESOS_ASESOR",
    "anulaciones": "FACTURACION_ANULACIONES_DECESOS",
    "siniestros": "SINIESTROS_DECESOS",
    "facturacion_salud": "FACTURACION_SALUD",
    "bajas_salud": "INFORME_BAJAS_SALUD",
    "facturacion_vida": "FACTURACION_VIDA",
    "mapeo": "MAPEO_MEDIADORES",
}

REQUIRED_BY_KEY = {
    "facturacion": REQUIRED_FACTURACION_COLUMNS,
    "facturacion_asesor": REQUIRED_FACTURACION_ASESOR_COLUMNS,
    "anulaciones": REQUIRED_ANULACIONES_COLUMNS,
    "siniestros": REQUIRED_SINIESTROS_COLUMNS,
    "facturacion_salud": REQUIRED_FACTURACION_SALUD_COLUMNS,
    "bajas_salud": REQUIRED_BAJAS_SALUD_COLUMNS,
    "facturacion_vida": REQUIRED_FACTURACION_VIDA_COLUMNS,
    "mapeo": REQUIRED_MAPEO_COLUMNS,
}

MONEY_HINTS = ("FACTURACION", "PRIMA", "IMPORTE", "SINIESTROS", "OBJETIVO")
PERCENT_HINTS = ("SINIESTRALIDAD", "PORCENTAJE", "CHURN")
INT_HINTS = ("POLIZAS", "RANKING", "PUESTO", "NUM_SINIESTROS")


def split_products(text: str) -> list[str]:
    return [item.strip() for item in str(text).split(",") if item.strip()]


def read_uploaded_excel(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame()
    return read_excel_all_sheets(uploaded_file)


def read_uploaded_many(uploaded_files) -> pd.DataFrame:
    if not uploaded_files:
        return pd.DataFrame()
    return read_excel_many_files(uploaded_files)


def validate_all(raw: dict[str, pd.DataFrame], primas_emitidas: pd.DataFrame, primas_anuladas: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    for key, required in REQUIRED_BY_KEY.items():
        df = raw.get(key, pd.DataFrame())
        name = FILE_HELP[key]
        if df.empty:
            errors.append(f"{name}: archivo vacío o no cargado")
            continue
        missing = validate_columns(df, required)
        if missing:
            errors.append(f"{name}: faltan columnas {', '.join(missing)}")

    for name, df in [("PRIMAS_EMITIDAS", primas_emitidas), ("PRIMAS_ANULADAS", primas_anuladas)]:
        if df.empty:
            errors.append(f"{name}: no has cargado ningún archivo")
            continue
        missing = validate_columns(df, REQUIRED_PRIMAS_COLUMNS)
        if missing:
            errors.append(f"{name}: faltan columnas {', '.join(missing)}")
    return errors


@st.cache_data(show_spinner=False)
def calculate_cached(
    facturacion_file,
    facturacion_asesor_file,
    anulaciones_file,
    siniestros_file,
    facturacion_salud_file,
    bajas_salud_file,
    facturacion_vida_file,
    mapeo_file,
    primas_emitidas_files,
    primas_anuladas_files,
    fecha_desde: date,
    fecha_hasta: date,
    excluded_products_tuple: tuple[str, ...],
) -> dict[str, pd.DataFrame]:
    raw = {
        "facturacion": read_uploaded_excel(facturacion_file),
        "facturacion_asesor": read_uploaded_excel(facturacion_asesor_file),
        "anulaciones": read_uploaded_excel(anulaciones_file),
        "siniestros": read_uploaded_excel(siniestros_file),
        "facturacion_salud": read_uploaded_excel(facturacion_salud_file),
        "bajas_salud": read_uploaded_excel(bajas_salud_file),
        "facturacion_vida": read_uploaded_excel(facturacion_vida_file),
        "mapeo": read_uploaded_excel(mapeo_file),
    }
    raw_primas_emitidas = read_uploaded_many(primas_emitidas_files)
    raw_primas_anuladas = read_uploaded_many(primas_anuladas_files)

    errors = validate_all(raw, raw_primas_emitidas, raw_primas_anuladas)
    if errors:
        raise ValueError("\n".join(errors))

    excluded_products = list(excluded_products_tuple)
    mapeo = prepare_mapeo_data(raw["mapeo"])

    sheet_summary = pd.concat(
        [
            build_sheet_summary(raw["facturacion"], "FACTURACION_DECESOS"),
            build_sheet_summary(raw["facturacion_asesor"], "FACTURACION_DECESOS_ASESOR"),
            build_sheet_summary(raw["anulaciones"], "FACTURACION_ANULACIONES_DECESOS"),
            build_sheet_summary(raw["siniestros"], "SINIESTROS_DECESOS"),
            build_sheet_summary(raw_primas_emitidas, "PRIMAS_EMITIDAS"),
            build_sheet_summary(raw_primas_anuladas, "PRIMAS_ANULADAS"),
            build_sheet_summary(raw["facturacion_salud"], "FACTURACION_SALUD"),
            build_sheet_summary(raw["bajas_salud"], "BAJAS_SALUD"),
            build_sheet_summary(raw["facturacion_vida"], "FACTURACION_VIDA"),
            build_sheet_summary(raw["mapeo"], "MAPEO_MEDIADORES"),
        ],
        ignore_index=True,
    )

    ranking, altas_detail, anulaciones_detail, siniestros_detail, primas_emitidas_detail, primas_anuladas_detail = calculate_ranking(
        raw["facturacion"],
        raw["anulaciones"],
        raw["siniestros"],
        raw_primas_emitidas,
        raw_primas_anuladas,
        fecha_desde,
        fecha_hasta,
        excluded_products,
    )
    ranking = add_mapeo_to_ranking(ranking, mapeo)

    ranking_asesor_decesos, altas_asesor_detail, anulaciones_asesor_detail = calculate_ranking_asesor_decesos(
        raw["facturacion_asesor"],
        raw["anulaciones"],
        fecha_desde,
        fecha_hasta,
        excluded_products,
    )

    ranking_salud, salud_bruta_detail, salud_anulaciones_detail = calculate_facturacion_salud(
        raw["facturacion_salud"],
        raw["bajas_salud"],
        fecha_desde,
        fecha_hasta,
    )
    ranking_salud = add_mapeo_to_simple_ranking(ranking_salud, mapeo)

    ranking_vida, vida_bruta_detail, vida_anulaciones_detail = calculate_facturacion_vida(
        raw["facturacion_vida"],
        raw["bajas_salud"],
        fecha_desde,
        fecha_hasta,
    )
    ranking_vida = add_mapeo_to_simple_ranking(ranking_vida, mapeo)

    integer_columns = [
        "POLIZAS_ALTAS", "POLIZAS_ANULADAS", "POLIZAS_NETAS",
        "POLIZAS_SALUD_BRUTAS", "POLIZAS_SALUD_ANULADAS", "POLIZAS_SALUD_NETAS",
        "POLIZAS_SALUD_ANULADAS_NUEVA_PRODUCCION", "POLIZAS_SALUD_NETAS_NUEVA_PRODUCCION",
        "POLIZAS_VIDA_BRUTAS", "POLIZAS_VIDA_ANULADAS", "POLIZAS_VIDA_NETAS",
        "POLIZAS_VIDA_ANULADAS_NUEVA_PRODUCCION", "POLIZAS_VIDA_NETAS_NUEVA_PRODUCCION",
        "NUM_SINIESTROS",
    ]

    for dataframe in [ranking, ranking_salud, ranking_vida, ranking_asesor_decesos]:
        for column in integer_columns:
            if column in dataframe.columns:
                dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce").fillna(0).round(0).astype(int)

    return {
        "ranking_decesos_top10": build_ranking_decesos_top10(ranking),
        "ranking_asesor_decesos_top10": ranking_asesor_decesos,
        "ranking_salud_top10": build_ranking_salud_top10(ranking_salud, ranking),
        "ranking_vida_top10": build_ranking_vida_top10(ranking_vida, ranking),
        "ranking": ranking,
        "ranking_asesor_decesos": ranking_asesor_decesos,
        "ranking_salud": ranking_salud,
        "ranking_vida": ranking_vida,
        "sheet_summary": sheet_summary,
        "altas_detail": altas_detail,
        "anulaciones_detail": anulaciones_detail,
        "altas_asesor_detail": altas_asesor_detail,
        "anulaciones_asesor_detail": anulaciones_asesor_detail,
        "siniestros_detail": siniestros_detail,
        "primas_emitidas_detail": primas_emitidas_detail,
        "primas_anuladas_detail": primas_anuladas_detail,
        "salud_bruta_detail": salud_bruta_detail,
        "salud_anulaciones_detail": salud_anulaciones_detail,
        "vida_bruta_detail": vida_bruta_detail,
        "vida_anulaciones_detail": vida_anulaciones_detail,
        "excel_args": {
            "ranking": ranking,
            "ranking_salud": ranking_salud,
            "ranking_vida": ranking_vida,
            "ranking_asesor_decesos": ranking_asesor_decesos,
            "ranking_decesos_top10": build_ranking_decesos_top10(ranking),
            "ranking_salud_top10": build_ranking_salud_top10(ranking_salud, ranking),
            "ranking_vida_top10": build_ranking_vida_top10(ranking_vida, ranking),
            "ranking_asesor_decesos_top10": ranking_asesor_decesos,
            "altas_detail": altas_detail,
            "anulaciones_detail": anulaciones_detail,
            "altas_asesor_detail": altas_asesor_detail,
            "anulaciones_asesor_detail": anulaciones_asesor_detail,
            "siniestros_detail": siniestros_detail,
            "primas_emitidas_detail": primas_emitidas_detail,
            "primas_anuladas_detail": primas_anuladas_detail,
            "salud_bruta_detail": salud_bruta_detail,
            "salud_anulaciones_detail": salud_anulaciones_detail,
            "vida_bruta_detail": vida_bruta_detail,
            "vida_anulaciones_detail": vida_anulaciones_detail,
            "sheet_summary": sheet_summary,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "excluded_products": excluded_products,
        }
    }


def as_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig").encode("utf-8-sig")


def format_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in result.columns:
        upper = str(col).upper()
        if any(x in upper for x in MONEY_HINTS):
            result[col] = pd.to_numeric(result[col], errors="ignore")
        elif any(x in upper for x in PERCENT_HINTS):
            result[col] = pd.to_numeric(result[col], errors="ignore")
    return result


def show_table(name: str, df: pd.DataFrame) -> None:
    st.subheader(name)
    if df.empty:
        st.info("No hay datos para mostrar.")
        return

    with st.expander("Ordenar/seleccionar columnas", expanded=False):
        default_cols = list(df.columns)
        selected_cols = st.multiselect(
            "Columnas visibles y orden",
            options=default_cols,
            default=default_cols,
            key=f"cols_{name}",
            help="Quita columnas y vuelve a seleccionarlas en el orden que quieras ver/exportar.",
        )
        sort_col = st.selectbox("Ordenar por", options=[""] + selected_cols, key=f"sort_{name}")
        ascending = st.checkbox("Ascendente", value=False, key=f"asc_{name}")

    shown = df[selected_cols].copy() if selected_cols else df.copy()
    if sort_col:
        shown = shown.sort_values(sort_col, ascending=ascending)

    st.dataframe(format_dataframe_for_display(shown), use_container_width=True, hide_index=True)

    c1, c2 = st.columns([1, 4])
    with c1:
        st.download_button(
            "Descargar CSV",
            data=as_csv_bytes(shown),
            file_name=f"{name.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            key=f"csv_{name}",
        )


st.title("📊 Ranking agentes - Decesos + Salud + Vida")
st.caption("Versión Streamlit con lógica de ranking_core, Salud/Vida, nueva producción y exportación CSV/Excel.")

with st.sidebar:
    st.header("Parámetros")
    fecha_desde = st.date_input("Fecha desde", value=date(DEFAULT_RANKING_DATE.year, 1, 1), format="DD/MM/YYYY")
    fecha_hasta = st.date_input("Fecha hasta", value=DEFAULT_RANKING_DATE, format="DD/MM/YYYY")
    excluded_products_text = st.text_input("Productos excluidos Decesos", value=", ".join(DEFAULT_EXCLUDED_PRODUCTS))
    excluded_products = tuple(split_products(excluded_products_text))

    st.divider()
    st.header("Archivos")
    facturacion_file = st.file_uploader("FACTURACION_DECESOS", type=["xlsx", "xls", "xlsm", "xlsb"], key="facturacion")
    facturacion_asesor_file = st.file_uploader("FACTURACION_DECESOS_ASESOR", type=["xlsx", "xls", "xlsm", "xlsb"], key="facturacion_asesor")
    anulaciones_file = st.file_uploader("FACTURACION_ANULACIONES_DECESOS", type=["xlsx", "xls", "xlsm", "xlsb"], key="anulaciones")
    siniestros_file = st.file_uploader("SINIESTROS_DECESOS", type=["xlsx", "xls", "xlsm", "xlsb"], key="siniestros")
    facturacion_salud_file = st.file_uploader("FACTURACION_SALUD", type=["xlsx", "xls", "xlsm", "xlsb"], key="facturacion_salud")
    bajas_salud_file = st.file_uploader("INFORME_BAJAS_SALUD", type=["xlsx", "xls", "xlsm", "xlsb"], key="bajas_salud")
    facturacion_vida_file = st.file_uploader("FACTURACION_VIDA", type=["xlsx", "xls", "xlsm", "xlsb"], key="facturacion_vida")
    mapeo_file = st.file_uploader("MAPEO_MEDIADORES", type=["xlsx", "xls", "xlsm", "xlsb"], key="mapeo")
    primas_emitidas_files = st.file_uploader("PRIMAS_EMITIDAS (uno o varios)", type=["xlsx", "xls", "xlsm", "xlsb"], accept_multiple_files=True, key="primas_emitidas")
    primas_anuladas_files = st.file_uploader("PRIMAS_ANULADAS (uno o varios)", type=["xlsx", "xls", "xlsm", "xlsb"], accept_multiple_files=True, key="primas_anuladas")

    calculate_btn = st.button("Calcular ranking", type="primary", use_container_width=True)

required_loaded = all([
    facturacion_file, facturacion_asesor_file, anulaciones_file, siniestros_file,
    facturacion_salud_file, bajas_salud_file, facturacion_vida_file, mapeo_file,
    primas_emitidas_files, primas_anuladas_files,
])

if fecha_desde > fecha_hasta:
    st.error("La fecha desde no puede ser posterior a la fecha hasta.")
elif not required_loaded:
    st.info("Carga todos los archivos en la barra lateral y pulsa Calcular ranking.")
elif calculate_btn or "ranking_data" not in st.session_state:
    try:
        with st.spinner("Calculando..."):
            st.session_state["ranking_data"] = calculate_cached(
                facturacion_file,
                facturacion_asesor_file,
                anulaciones_file,
                siniestros_file,
                facturacion_salud_file,
                bajas_salud_file,
                facturacion_vida_file,
                mapeo_file,
                primas_emitidas_files,
                primas_anuladas_files,
                fecha_desde,
                fecha_hasta,
                excluded_products,
            )
        st.success("Cálculo terminado correctamente.")
    except Exception as exc:
        st.error(str(exc))
        with st.expander("Detalle técnico"):
            st.code(traceback.format_exc())

if "ranking_data" in st.session_state:
    data = st.session_state["ranking_data"]

    ranking = data["ranking"]
    ranking_salud = data["ranking_salud"]
    ranking_vida = data["ranking_vida"]

    total_neta = float(ranking["FACTURACION_NETA"].sum()) if not ranking.empty and "FACTURACION_NETA" in ranking else 0.0
    total_primas_netas = float(ranking["PRIMAS_NETAS"].sum()) if not ranking.empty and "PRIMAS_NETAS" in ranking else 0.0
    total_siniestros = float(ranking["IMPORTE_SINIESTROS"].sum()) if not ranking.empty and "IMPORTE_SINIESTROS" in ranking else 0.0
    siniestralidad_total = total_siniestros / total_primas_netas if total_primas_netas > 0 else 0.0
    total_salud_neta = float(ranking_salud["FACTURACION_SALUD_NETA"].sum()) if not ranking_salud.empty and "FACTURACION_SALUD_NETA" in ranking_salud else 0.0
    total_vida_neta = float(ranking_vida["FACTURACION_VIDA_NETA"].sum()) if not ranking_vida.empty and "FACTURACION_VIDA_NETA" in ranking_vida else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Facturación neta Decesos", format_euro(total_neta))
    m2.metric("Siniestralidad Decesos", format_percent(siniestralidad_total))
    m3.metric("Facturación neta Salud", format_euro(total_salud_neta))
    m4.metric("Facturación neta Vida", format_euro(total_vida_neta))

    excel_bytes = dataframe_to_excel(**data["excel_args"])
    st.download_button(
        "📥 Descargar Excel completo",
        data=excel_bytes,
        file_name=f"ranking_agentes_{fecha_hasta.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    tabs = st.tabs([
        "Ranking Decesos", "Ranking Asesores", "Ranking Salud", "Ranking Vida",
        "Completo Decesos", "Facturación Salud", "Facturación Vida", "Detalles", "Hojas leídas"
    ])

    with tabs[0]:
        show_table("Ranking Decesos", data["ranking_decesos_top10"])
    with tabs[1]:
        show_table("Ranking Asesores", data["ranking_asesor_decesos"])
    with tabs[2]:
        show_table("Ranking Salud", data["ranking_salud_top10"])
    with tabs[3]:
        show_table("Ranking Vida", data["ranking_vida_top10"])
    with tabs[4]:
        show_table("Completo Decesos", data["ranking"])
    with tabs[5]:
        show_table("Facturación Salud", data["ranking_salud"])
    with tabs[6]:
        show_table("Facturación Vida", data["ranking_vida"])
    with tabs[7]:
        detail_name = st.selectbox(
            "Detalle",
            [
                "altas_detail", "anulaciones_detail", "altas_asesor_detail", "anulaciones_asesor_detail",
                "siniestros_detail", "primas_emitidas_detail", "primas_anuladas_detail",
                "salud_bruta_detail", "salud_anulaciones_detail", "vida_bruta_detail", "vida_anulaciones_detail",
            ],
        )
        show_table(detail_name, data[detail_name])
    with tabs[8]:
        show_table("Hojas leídas", data["sheet_summary"])
