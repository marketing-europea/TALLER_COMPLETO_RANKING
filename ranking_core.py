from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd


DEFAULT_RANKING_DATE = date(2026, 1, 30)
DEFAULT_EXCLUDED_PRODUCTS = ("D600", "D460")
SINIESTRALIDAD_MAXIMA = 0.25

# Codigos que NO deben aparecer en el ranking de asesores de Decesos.
# Son mediadores / codigos internos que vienen en el campo de red comercial,
# pero no son asesores reales del call center.
EXCLUDED_ASESOR_CODES = {
    "28005",   # Selectra
    "34400",   # Roams
    "29403",   # Adity
    "105-0000",# Servicios funerarios
    "48400",   # Asegurogintza, S.L.
    "08417-001",   # Bolanq
    "11013",   # Viepa
    "436",   # Cohebu
    "110-G010",   # OFICINA

    # NUEVOS
    "Sin codigo",
    "Sin codigo red",
    "",
}

EXCLUDED_ASESOR_PREFIXES = ("100-",)

# ============================================================
# OBJETIVOS Y REGLAS 2026
# ============================================================

# Mediadores que en 2025 hicieron mas de 50k y por tanto son Liga Elite en 2026.
# Se normalizan quitando ceros a la izquierda, por eso "00100" tambien matchea con "100".
LIGA_ELITE_CODES_2025 = {"46407", "28005", "34400", "100"}

# Decesos
DECESOS_OBJETIVO_PRO = 30000.0
DECESOS_OBJETIVO_ELITE = 60000.0

# Salud
# Opcion 1: 1 plaza doble = 25k Salud + 12k Decesos
# Opcion 2: 2 plazas dobles = 80k Salud + 4k Decesos
SALUD_PLAZA_1_MINIMA = 25000.0
SALUD_PLAZA_1_DECESOS_MINIMA = 12000.0
SALUD_PLAZA_2_MINIMA = 80000.0
SALUD_PLAZA_2_DECESOS_MINIMA = 4000.0

# Vida
# Plaza doble = 10k Vida
# O tambien plaza doble = 5k Vida + 5k Decesos
VIDA_PLAZA_DOBLE_MINIMA = 10000.0
VIDA_PLAZA_DOBLE_CON_DECESOS_MINIMA = 5000.0
VIDA_DECESOS_MINIMA = 5000.0

COLOR_DECESOS = "#f32735"
COLOR_SALUD = "#5271ff"
COLOR_VIDA = "#ffb4ab"
COLOR_ASESORES = "#7c3aed"

REQUIRED_FACTURACION_COLUMNS = ("PRODUCTO", "POLIALTA", "POLIZA", "MEDIADOR", "PRIMA NETA")
REQUIRED_FACTURACION_ASESOR_COLUMNS = ("PRODUCTO", "POLIALTA", "POLIZA", "COMERCIAL", "PRIMA NETA")
REQUIRED_ANULACIONES_COLUMNS = ("PRODUCTO", "FECHA EMISION", "POLIZA", "MEDIADOR", "PRIMA NETA", "CAUSA")
REQUIRED_SINIESTROS_COLUMNS = ("PRODUCTO", "CODIMEDI", "FECHOCUR", "RESERACT", "PAGOSPDT")
REQUIRED_PRIMAS_COLUMNS = ("MEDIADOR", "POLIPNET")
REQUIRED_FACTURACION_SALUD_COLUMNS = ("PRODUCTO", "IDPOLIZA", "MEDIADOR", "POLIEFEC", "PRIMA NETA", "FECHBAJA")
REQUIRED_BAJAS_SALUD_COLUMNS = ("POLIZA", "DES_PRODUCTO", "FEC_EFECTO_BAJA", "FEC_GRABACION_BAJA", "FEC_EFECTO_REACTIV")
REQUIRED_MAPEO_COLUMNS = ("CODIMEDI", "NOMBCOME", "Responsable","POBLACION")
REQUIRED_FACTURACION_VIDA_COLUMNS = ("NUMERO", "CODIMEDI", "FECHALTA", "PRIMATOTAL")

AGENCY_NAME_COLUMNS = (
    "NOMBRE AGENCIA",
    "NOMBRE_AGENCIA",
    "AGENCIA",
    "NOMBRE MEDIADOR",
    "NOM MEDIADOR",
    "MEDIADOR NOMBRE",
)

DEPENDENCY_COLUMNS = ("SECTOCOB", "SECTOR", "DEPENDENCIA")


def parse_spanish_number(value: object) -> float:
    if pd.isna(value):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace("\xa0", " ").strip()
    text = re.sub(r"[^\d,.\-]", "", text)

    if not text or text in {"-", ",", "."}:
        return 0.0

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_product(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def normalize_text(value: object, default: str = "") -> str:
    if pd.isna(value) or str(value).strip() == "":
        return default

    text = str(value).strip()

    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]

    return text


def normalize_reason_text(value: object) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip().upper()
    replacements = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U"}

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def normalize_agent(value: object) -> str:
    return normalize_text(value, "Sin mediador")


def normalize_code_for_liga(value: object) -> str:
    code = normalize_text(value, "")
    return code.lstrip("0") or "0"


def first_existing_column(columns: list[str] | pd.Index, options: tuple[str, ...]) -> str | None:
    normalized = {str(column).strip().upper(): str(column).strip() for column in columns}

    for option in options:
        column = normalized.get(option.upper())
        if column is not None:
            return column

    return None

def normalize_column_key(value: object) -> str:
    text = str(value).strip().upper()
    replacements = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_column_fuzzy(columns: list[str] | pd.Index, candidates: tuple[str, ...]) -> str | None:
    normalized = {normalize_column_key(column): str(column).strip() for column in columns}

    for candidate in candidates:
        key = normalize_column_key(candidate)
        if key in normalized:
            return normalized[key]

    # Para el Excel de asesor a veces la cabecera aparece acortada visualmente como CODIGO R.
    for key, original in normalized.items():
        if key.startswith("CODIGO R") or key.startswith("CODIGO RED"):
            return original

    return None


def require_column_fuzzy(df: pd.DataFrame, candidates: tuple[str, ...], label: str) -> str:
    column = find_column_fuzzy(df.columns, candidates)
    if column is None:
        raise ValueError(f"Falta la columna {label}. Columnas leidas: {', '.join(map(str, df.columns))}")
    return column



def first_non_empty(values: pd.Series) -> str:
    for value in values:
        if not pd.isna(value) and str(value).strip() != "":
            return str(value).strip()

    return ""


def in_date_range(series: pd.Series, fecha_desde: date, fecha_hasta: date) -> pd.Series:
    return series.notna() & series.dt.date.ge(fecha_desde) & series.dt.date.le(fecha_hasta)


def calculate_progress(value: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return value / target


def read_excel_all_sheets(excel_file) -> pd.DataFrame:
    sheets = pd.read_excel(excel_file, sheet_name=None, dtype=str)
    frames = []

    if isinstance(excel_file, (str, Path)):
        file_name = Path(excel_file).name
    else:
        file_name = getattr(excel_file, "name", "archivo")

    for sheet_name, sheet_df in sheets.items():
        sheet_df = sheet_df.copy()
        sheet_df.columns = [str(column).strip() for column in sheet_df.columns]
        sheet_df["ARCHIVO_ORIGEN"] = file_name
        sheet_df["HOJA_ORIGEN"] = sheet_name
        frames.append(sheet_df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def read_excel_many_files(excel_files) -> pd.DataFrame:
    frames = []

    for excel_file in excel_files or []:
        file_df = read_excel_all_sheets(excel_file)
        if not file_df.empty:
            frames.append(file_df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def validate_columns(df: pd.DataFrame, required_columns: tuple[str, ...]) -> list[str]:
    return [column for column in required_columns if column not in df.columns]


def prepare_mapeo_data(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    work["AGENTE"] = work["CODIMEDI"].apply(normalize_agent)
    work["CODIMEDI"] = work["CODIMEDI"].apply(normalize_agent)
    work["NOMBRE_AGENCIA_MAPEO"] = work["NOMBCOME"].apply(lambda value: normalize_text(value, ""))
    work["RESPONSABLE"] = work["Responsable"].apply(lambda value: normalize_text(value, "Sin responsable"))
    work["POBLACION"] = work["POBLACION"].apply(lambda value: normalize_text(value, "Sin población"))

    return (
        work[["AGENTE", "CODIMEDI", "NOMBRE_AGENCIA_MAPEO", "RESPONSABLE", "POBLACION"]]
        .drop_duplicates("AGENTE")
        .copy()
    )


def add_mapeo_to_ranking(ranking: pd.DataFrame, mapeo: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return ranking.copy()

    result = ranking.copy()
    result["AGENTE"] = result["AGENTE"].apply(normalize_agent)

    if not mapeo.empty:
        result = pd.merge(result, mapeo, on="AGENTE", how="left")
    else:
        result["CODIMEDI"] = result["AGENTE"]
        result["NOMBRE_AGENCIA_MAPEO"] = ""
        result["RESPONSABLE"] = "Sin responsable"
        result["POBLACION"] = "Sin población"

    result["CODIMEDI"] = result["CODIMEDI"].fillna(result["AGENTE"])
    result["NOMBRE_AGENCIA"] = [
        mapped if not pd.isna(mapped) and str(mapped).strip() != "" else original
        for mapped, original in zip(result["NOMBRE_AGENCIA_MAPEO"], result["NOMBRE_AGENCIA"])
    ]
    result["RESPONSABLE"] = result["RESPONSABLE"].fillna("Sin responsable")
    result["POBLACION"] = result["POBLACION"].fillna("Sin población")

    return result.drop(columns=["NOMBRE_AGENCIA_MAPEO"], errors="ignore")


def add_mapeo_to_simple_ranking(ranking: pd.DataFrame, mapeo: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return ranking.copy()

    result = ranking.copy()
    result["AGENTE"] = result["AGENTE"].apply(normalize_agent)

    if not mapeo.empty:
        result = pd.merge(result, mapeo, on="AGENTE", how="left")
    else:
        result["CODIMEDI"] = result["AGENTE"]
        result["NOMBRE_AGENCIA_MAPEO"] = ""
        result["RESPONSABLE"] = "Sin responsable"
        result["POBLACION"] = "Sin población"

    result["CODIMEDI"] = result["CODIMEDI"].fillna(result["AGENTE"])
    result["NOMBRE_AGENCIA"] = [
        mapped if not pd.isna(mapped) and str(mapped).strip() != "" else agent
        for mapped, agent in zip(result["NOMBRE_AGENCIA_MAPEO"], result["AGENTE"])
    ]
    result["RESPONSABLE"] = result["RESPONSABLE"].fillna("Sin responsable")
    result["POBLACION"] = result["POBLACION"].fillna("Sin población")

    return result.drop(columns=["NOMBRE_AGENCIA_MAPEO"], errors="ignore")


def prepare_decesos_data(df: pd.DataFrame, date_column: str, movement: str) -> pd.DataFrame:
    work = df.copy()

    agency_name_column = first_existing_column(work.columns, AGENCY_NAME_COLUMNS)
    dependency_column = first_existing_column(work.columns, DEPENDENCY_COLUMNS)

    work["MOVIMIENTO"] = movement
    work["PRODUCTO_NORMALIZADO"] = work["PRODUCTO"].apply(normalize_product)
    work["AGENTE"] = work["MEDIADOR"].apply(normalize_agent)

    if agency_name_column:
        agency_names = work[agency_name_column].apply(lambda value: normalize_text(value, ""))
        work["NOMBRE_AGENCIA"] = [
            agency_name if agency_name else agent
            for agency_name, agent in zip(agency_names, work["AGENTE"])
        ]
    else:
        work["NOMBRE_AGENCIA"] = work["AGENTE"]

    if dependency_column:
        work["DEPENDENCIA"] = work[dependency_column].apply(lambda value: normalize_text(value, "Sin dependencia"))
    else:
        work["DEPENDENCIA"] = "Sin dependencia"

    work["FECHA_MOVIMIENTO"] = pd.to_datetime(work[date_column], dayfirst=True, errors="coerce")
    work["ANIO_MOVIMIENTO"] = work["FECHA_MOVIMIENTO"].dt.year
    work["MES_MOVIMIENTO"] = work["FECHA_MOVIMIENTO"].dt.month
    work["PRIMA_NETA_VALOR"] = work["PRIMA NETA"].apply(parse_spanish_number)

    return work


def filter_movements(
    df: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
    excluded_products: list[str],
    date_column: str,
    movement: str,
) -> pd.DataFrame:
    work = prepare_decesos_data(df, date_column, movement)
    excluded = {normalize_product(product) for product in excluded_products}

    mask = (
        in_date_range(work["FECHA_MOVIMIENTO"], fecha_desde, fecha_hasta)
        & ~work["PRODUCTO_NORMALIZADO"].isin(excluded)
    )

    if movement == "ANULACION":
        motivo = work["MOTIVO"].apply(normalize_reason_text) if "MOTIVO" in work.columns else pd.Series("", index=work.index)
        causa = work["CAUSA"].apply(normalize_reason_text) if "CAUSA" in work.columns else pd.Series("", index=work.index)

        excluded_by_motivo = (
            motivo.str.startswith("DEFUNCION DEL ULTIMO O UNICO ASEGURADO", na=False)
            | motivo.str.startswith("DEFUNCION (QUEDAN MAS ASEGURADOS PERO NO LA QUIEREN)", na=False)
            | motivo.str.startswith("SINIESTRO TOTAL", na=False)
            | motivo.str.startswith("DEFUNCION", na=False)
        )

        excluded_by_causa = (
            causa.str.startswith("DEFUNCION", na=False)
            | causa.str.startswith("INDIVIDUAL POR SINIESTRO", na=False)
        )

        mask = mask & ~excluded_by_motivo & ~excluded_by_causa

    return work[mask].copy()


def aggregate_movements(detail: pd.DataFrame, amount_column: str, count_column: str) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=["AGENTE", "NOMBRE_AGENCIA", "DEPENDENCIA", amount_column, count_column])

    return (
        detail.groupby("AGENTE", dropna=False)
        .agg(
            NOMBRE_AGENCIA=("NOMBRE_AGENCIA", first_non_empty),
            DEPENDENCIA=("DEPENDENCIA", first_non_empty),
            **{
                amount_column: ("PRIMA_NETA_VALOR", "sum"),
                count_column: ("POLIZA", "count"),
            },
        )
        .reset_index()
    )


def normalize_policy(value: object) -> str:
    return normalize_text(value, "")


def prepare_decesos_asesor_data(df: pd.DataFrame, date_column: str = "POLIALTA", movement: str = "ALTA") -> pd.DataFrame:
    """Prepara el Excel FACTURACION_DECESOS_ASESOR.

    IMPORTANTE: este ranking NO agrupa por MEDIADOR/CODIMEDI.
    Agrupa exclusivamente por las dos ultimas columnas del Excel:
    - CODIGO RED COMERCIAL
    - COMERCIAL
    """
    work = df.copy()

    producto_col = require_column_fuzzy(work, ("PRODUCTO",), "PRODUCTO")
    poliza_col = require_column_fuzzy(work, ("POLIZA",), "POLIZA")
    codigo_red_col = require_column_fuzzy(
        work,
        ("CODIGO RED COMERCIAL", "CODIGO RED", "CODIGO R", "CODIGO_RED_COMERCIAL"),
        "CODIGO RED COMERCIAL",
    )
    comercial_col = require_column_fuzzy(work, ("COMERCIAL",), "COMERCIAL")
    prima_col = require_column_fuzzy(work, ("PRIMA NETA", "PRIMA NE", "PRIMA_NETA"), "PRIMA NETA")
    fecha_col = require_column_fuzzy(work, (date_column, "POLIALTA", "FECHA ALTA"), date_column)

    work["MOVIMIENTO"] = movement
    work["PRODUCTO_NORMALIZADO"] = work[producto_col].apply(normalize_product)
    work["POLIZA_NORMALIZADA"] = work[poliza_col].apply(normalize_policy)
    work["CODIGO_RED_COMERCIAL"] = work[codigo_red_col].apply(lambda value: normalize_text(value, "Sin codigo red"))
    work["COMERCIAL"] = work[comercial_col].apply(lambda value: normalize_text(value, "Sin asesor"))
    work["FECHA_MOVIMIENTO"] = pd.to_datetime(work[fecha_col], dayfirst=True, errors="coerce")
    work["ANIO_MOVIMIENTO"] = work["FECHA_MOVIMIENTO"].dt.year
    work["MES_MOVIMIENTO"] = work["FECHA_MOVIMIENTO"].dt.month
    work["PRIMA_NETA_VALOR"] = work[prima_col].apply(parse_spanish_number)

    # Clave tecnica solo para unir altas/anulaciones. La agrupacion real se hace por las 2 columnas.
    work["ASESOR_KEY"] = work["CODIGO_RED_COMERCIAL"] + " - " + work["COMERCIAL"]

    return work


def prepare_asesor_lookup(facturacion_asesor_df: pd.DataFrame) -> pd.DataFrame:
    work = prepare_decesos_asesor_data(facturacion_asesor_df)
    lookup = (
        work[["POLIZA_NORMALIZADA", "CODIGO_RED_COMERCIAL", "COMERCIAL", "ASESOR_KEY"]]
        .dropna(subset=["POLIZA_NORMALIZADA"])
        .drop_duplicates("POLIZA_NORMALIZADA")
        .copy()
    )
    return lookup


def filter_movements_asesor(
    df: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
    excluded_products: list[str],
) -> pd.DataFrame:
    work = prepare_decesos_asesor_data(df, "POLIALTA", "ALTA")
    excluded = {normalize_product(product) for product in excluded_products}

    mask = (
        in_date_range(work["FECHA_MOVIMIENTO"], fecha_desde, fecha_hasta)
        & ~work["PRODUCTO_NORMALIZADO"].isin(excluded)
    )

    return work[mask].copy()


def aggregate_movements_asesor(detail: pd.DataFrame, amount_column: str, count_column: str) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=["CODIGO_RED_COMERCIAL", "COMERCIAL", amount_column, count_column])

    # Agrupacion REAL del ranking de asesor: codigo red comercial + comercial.
    return (
        detail.groupby(["CODIGO_RED_COMERCIAL", "COMERCIAL"], dropna=False)
        .agg(
            **{
                amount_column: ("PRIMA_NETA_VALOR", "sum"),
                count_column: ("POLIZA_NORMALIZADA", "nunique"),
            },
        )
        .reset_index()
    )




def exclude_non_callcenter_asesores(detail: pd.DataFrame) -> pd.DataFrame:
    """Quita mediadores/codigos internos del ranking de asesores."""
    if detail.empty or "CODIGO_RED_COMERCIAL" not in detail.columns:
        return detail.copy()

    result = detail.copy()
    codigo = result["CODIGO_RED_COMERCIAL"].astype(str).str.strip()

    mask_excluidos = codigo.isin(EXCLUDED_ASESOR_CODES)
    for prefix in EXCLUDED_ASESOR_PREFIXES:
        mask_excluidos = mask_excluidos | codigo.str.startswith(prefix, na=False)

    return result[~mask_excluidos].copy()

def calculate_ranking_asesor_decesos(
    facturacion_asesor_df: pd.DataFrame,
    anulaciones_df: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
    excluded_products: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    altas_detail = filter_movements_asesor(
        facturacion_asesor_df,
        fecha_desde,
        fecha_hasta,
        excluded_products,
    )

    # En ranking de asesores NO aplicamos la regla del 25/01.
    # Solo dejamos fuera anulaciones anteriores al 01/01 del año en curso.
    fecha_desde_anulaciones = max(
        fecha_desde,
        date(fecha_hasta.year, 1, 1)
    )
    anulaciones_base = filter_movements(
        anulaciones_df,
        fecha_desde_anulaciones,
        fecha_hasta,
        excluded_products,
        "FECHA EMISION",
        "ANULACION",
    )

    # SOLO PARA RANKING DE ASESORES:
    # Las anulaciones solo se imputan si la poliza fue dada de alta
    # en el mismo año del ranking segun POLIALTA.
    anio_ranking = fecha_hasta.year

    lookup_asesor = prepare_decesos_asesor_data(facturacion_asesor_df)
    lookup_asesor = lookup_asesor[
        lookup_asesor["FECHA_MOVIMIENTO"].dt.year == anio_ranking
    ].copy()

    lookup_asesor = (
        lookup_asesor[
            [
                "POLIZA_NORMALIZADA",
                "CODIGO_RED_COMERCIAL",
                "COMERCIAL",
                "ASESOR_KEY",
            ]
        ]
        .dropna(subset=["POLIZA_NORMALIZADA"])
        .drop_duplicates("POLIZA_NORMALIZADA")
        .copy()
    )

    anulaciones_base["POLIZA_NORMALIZADA"] = anulaciones_base["POLIZA"].apply(normalize_policy)

    # INNER: si la poliza anulada no esta en altas del mismo año, NO cuenta en asesores.
    anulaciones_detail = pd.merge(
        anulaciones_base,
        lookup_asesor,
        on="POLIZA_NORMALIZADA",
        how="inner",
    )

    if not anulaciones_detail.empty:
        anulaciones_detail["CODIGO_RED_COMERCIAL"] = anulaciones_detail["CODIGO_RED_COMERCIAL"].fillna("Sin codigo red")
        anulaciones_detail["COMERCIAL"] = anulaciones_detail["COMERCIAL"].fillna("Sin asesor")
        anulaciones_detail["ASESOR_KEY"] = anulaciones_detail["ASESOR_KEY"].fillna(
            anulaciones_detail["CODIGO_RED_COMERCIAL"] + " - " + anulaciones_detail["COMERCIAL"]
        )

    # Excluimos mediadores/codigos internos que aparecen en red comercial
    # pero no deben formar parte del ranking de asesores.
    altas_detail = exclude_non_callcenter_asesores(altas_detail)
    anulaciones_detail = exclude_non_callcenter_asesores(anulaciones_detail)

    altas = aggregate_movements_asesor(altas_detail, "FACTURACION_ALTAS_BRUTAS", "POLIZAS_ALTAS")
    anulaciones = aggregate_movements_asesor(anulaciones_detail, "FACTURACION_ANULACIONES", "POLIZAS_ANULADAS")

    ranking = pd.merge(
        altas,
        anulaciones,
        on=["CODIGO_RED_COMERCIAL", "COMERCIAL"],
        how="outer",
    )

    if ranking.empty:
        empty = pd.DataFrame(
            columns=[
                "RANKING_ASESOR", "CODIGO_RED_COMERCIAL", "COMERCIAL",
                "FACTURACION_ALTAS_BRUTAS", "FACTURACION_ANULACIONES", "FACTURACION_NETA",
                "POLIZAS_ALTAS", "POLIZAS_ANULADAS", "POLIZAS_NETAS",
                "CHURN_POLIZAS", "CHURN_FACTURACION",
            ]
        )
        return empty, altas_detail, anulaciones_detail

    ranking["CODIGO_RED_COMERCIAL"] = ranking["CODIGO_RED_COMERCIAL"].fillna("Sin codigo red")
    ranking["COMERCIAL"] = ranking["COMERCIAL"].fillna("Sin asesor")

    for column in [
        "FACTURACION_ALTAS_BRUTAS", "FACTURACION_ANULACIONES",
        "POLIZAS_ALTAS", "POLIZAS_ANULADAS",
    ]:
        if column in ranking.columns:
            ranking[column] = pd.to_numeric(ranking[column], errors="coerce").fillna(0)

    ranking["FACTURACION_NETA"] = ranking["FACTURACION_ALTAS_BRUTAS"] - ranking["FACTURACION_ANULACIONES"]
    ranking["POLIZAS_NETAS"] = ranking["POLIZAS_ALTAS"] - ranking["POLIZAS_ANULADAS"]
    ranking["CHURN_POLIZAS"] = [
        anuladas / altas if altas else 0.0
        for anuladas, altas in zip(ranking["POLIZAS_ANULADAS"], ranking["POLIZAS_ALTAS"])
    ]
    ranking["CHURN_FACTURACION"] = [
        anulacion / alta if alta else 0.0
        for anulacion, alta in zip(ranking["FACTURACION_ANULACIONES"], ranking["FACTURACION_ALTAS_BRUTAS"])
    ]

    ranking = ranking[
        [
            "CODIGO_RED_COMERCIAL", "COMERCIAL",
            "FACTURACION_ALTAS_BRUTAS", "FACTURACION_ANULACIONES", "FACTURACION_NETA",
            "POLIZAS_ALTAS", "POLIZAS_ANULADAS", "POLIZAS_NETAS",
            "CHURN_POLIZAS", "CHURN_FACTURACION",
        ]
    ].sort_values(
        ["FACTURACION_NETA", "CHURN_POLIZAS", "COMERCIAL"],
        ascending=[False, True, True],
    )

    ranking.insert(0, "RANKING_ASESOR", range(1, len(ranking) + 1))

    return ranking, altas_detail, anulaciones_detail


def build_ranking_asesor_decesos_top10(ranking_asesor: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "PUESTO_ASESOR", "CODIGO_RED_COMERCIAL", "COMERCIAL",
        "FACTURACION_NETA", "FACTURACION_ALTAS_BRUTAS", "FACTURACION_ANULACIONES",
        "POLIZAS_ALTAS", "POLIZAS_ANULADAS", "POLIZAS_NETAS",
        "CHURN_POLIZAS", "CHURN_FACTURACION",
    ]

    if ranking_asesor.empty:
        return pd.DataFrame(columns=columns)

    # IMPORTANTE: no limitamos a TOP 10.
    # La tabla debe mostrar TODOS los asesores/codigos red comercial.
    result = ranking_asesor.copy().sort_values(
        ["FACTURACION_NETA", "CHURN_POLIZAS", "COMERCIAL"],
        ascending=[False, True, True],
    )
    result.insert(0, "PUESTO_ASESOR", range(1, len(result) + 1))

    return result[columns]


def prepare_siniestros_data(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    work["PRODUCTO_NORMALIZADO"] = work["PRODUCTO"].apply(normalize_product)
    work["AGENTE"] = work["CODIMEDI"].apply(normalize_agent)
    work["FECHA_SINIESTRO"] = pd.to_datetime(work["FECHOCUR"], dayfirst=True, errors="coerce")
    work["ANIO_SINIESTRO"] = work["FECHA_SINIESTRO"].dt.year
    work["MES_SINIESTRO"] = work["FECHA_SINIESTRO"].dt.month

    work["RESERACT_VALOR"] = work["RESERACT"].apply(parse_spanish_number)
    work["PAGOSPDT_VALOR"] = work["PAGOSPDT"].apply(parse_spanish_number)
    work["EXPECACT_VALOR"] = work["EXPECACT"].apply(parse_spanish_number) if "EXPECACT" in work.columns else 0.0
    work["PAGOSRZD_VALOR"] = work["PAGOSRZD"].apply(parse_spanish_number) if "PAGOSRZD" in work.columns else 0.0
    work["COSTESIN_VALOR"] = work["COSTESIN"].apply(parse_spanish_number) if "COSTESIN" in work.columns else 0.0
    work["IMPORTE_SINIESTRO"] = work["RESERACT_VALOR"] + work["PAGOSPDT_VALOR"]

    return work


def filter_siniestros(df: pd.DataFrame, fecha_desde: date, fecha_hasta: date, excluded_products: list[str]) -> pd.DataFrame:
    work = prepare_siniestros_data(df)
    excluded = {normalize_product(product) for product in excluded_products}

    mask = (
        in_date_range(work["FECHA_SINIESTRO"], fecha_desde, fecha_hasta)
        & ~work["PRODUCTO_NORMALIZADO"].isin(excluded)
    )

    return work[mask].copy()


def aggregate_siniestros(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=["AGENTE", "IMPORTE_SINIESTROS", "NUM_SINIESTROS"])

    count_source = "NUMESINI" if "NUMESINI" in detail.columns else "IMPORTE_SINIESTRO"

    return (
        detail.groupby("AGENTE", dropna=False)
        .agg(
            IMPORTE_SINIESTROS=("IMPORTE_SINIESTRO", "sum"),
            NUM_SINIESTROS=(count_source, "count"),
        )
        .reset_index()
    )


def prepare_primas_data(df: pd.DataFrame, movement: str) -> pd.DataFrame:
    work = df.copy()

    work["MOVIMIENTO_PRIMA"] = movement
    work["AGENTE"] = work["MEDIADOR"].apply(normalize_agent)
    work["POLIPNET_VALOR"] = work["POLIPNET"].apply(parse_spanish_number)

    return work


def aggregate_primas(df: pd.DataFrame, movement: str, amount_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail = prepare_primas_data(df, movement)

    if detail.empty:
        return pd.DataFrame(columns=["AGENTE", amount_column]), detail

    aggregated = (
        detail.groupby("AGENTE", dropna=False)
        .agg(**{amount_column: ("POLIPNET_VALOR", "sum")})
        .reset_index()
    )

    return aggregated, detail


def calculate_ranking(
    facturacion_df: pd.DataFrame,
    anulaciones_df: pd.DataFrame,
    siniestros_df: pd.DataFrame,
    primas_emitidas_df: pd.DataFrame,
    primas_anuladas_df: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
    excluded_products: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:

    altas_detail = filter_movements(
        facturacion_df,
        fecha_desde,
        fecha_hasta,
        excluded_products,
        "POLIALTA",
        "ALTA",
    )

    # En 2026, las anulaciones anteriores al 25/01/2026 pertenecen a 2025
    fecha_desde_anulaciones = fecha_desde
    if fecha_hasta >= date(2026, 1, 24):
        fecha_desde_anulaciones = max(fecha_desde, date(2026, 1, 25))

    anulaciones_detail = filter_movements(
        anulaciones_df,
        fecha_desde_anulaciones,
        fecha_hasta,
        excluded_products,
        "FECHA EMISION",
        "ANULACION",
    )

    siniestros_detail = filter_siniestros(
        siniestros_df,
        fecha_desde,
        fecha_hasta,
        excluded_products,
    )

    altas = aggregate_movements(altas_detail, "FACTURACION_ALTAS_BRUTAS", "POLIZAS_ALTAS")
    anulaciones = aggregate_movements(anulaciones_detail, "FACTURACION_ANULACIONES", "POLIZAS_ANULADAS")
    siniestros = aggregate_siniestros(siniestros_detail)

    primas_emitidas, primas_emitidas_detail = aggregate_primas(primas_emitidas_df, "EMITIDA", "PRIMAS_EMITIDAS")
    primas_anuladas, primas_anuladas_detail = aggregate_primas(primas_anuladas_df, "ANULADA", "PRIMAS_ANULADAS")

    ranking = pd.merge(
        altas,
        anulaciones,
        on="AGENTE",
        how="outer",
        suffixes=("_ALTAS", "_ANULACIONES"),
    )

    if ranking.empty:
        empty = pd.DataFrame(
            columns=[
                "RANKING", "AGENTE", "NOMBRE_AGENCIA", "DEPENDENCIA",
                "FACTURACION_ALTAS_BRUTAS", "FACTURACION_ANULACIONES", "FACTURACION_NETA",
                "PRIMAS_EMITIDAS", "PRIMAS_ANULADAS", "PRIMAS_NETAS",
                "IMPORTE_SINIESTROS", "SINIESTRALIDAD", "CUMPLE_SINIESTRALIDAD",
                "POLIZAS_ALTAS", "POLIZAS_ANULADAS", "POLIZAS_NETAS",
                "NUM_SINIESTROS", "PRIMA_MEDIA_NETA",
            ]
        )
        return empty, altas_detail, anulaciones_detail, siniestros_detail, primas_emitidas_detail, primas_anuladas_detail

    ranking["NOMBRE_AGENCIA"] = ranking["NOMBRE_AGENCIA_ALTAS"].combine_first(ranking["NOMBRE_AGENCIA_ANULACIONES"])
    ranking["DEPENDENCIA"] = ranking["DEPENDENCIA_ALTAS"].combine_first(ranking["DEPENDENCIA_ANULACIONES"])

    ranking["NOMBRE_AGENCIA"] = [
        name if not pd.isna(name) and str(name).strip() != "" else agent
        for name, agent in zip(ranking["NOMBRE_AGENCIA"], ranking["AGENTE"])
    ]
    ranking["DEPENDENCIA"] = ranking["DEPENDENCIA"].fillna("Sin dependencia")

    ranking = pd.merge(ranking, siniestros, on="AGENTE", how="left")
    ranking = pd.merge(ranking, primas_emitidas, on="AGENTE", how="left")
    ranking = pd.merge(ranking, primas_anuladas, on="AGENTE", how="left")

    numeric_columns = [
        "FACTURACION_ALTAS_BRUTAS",
        "FACTURACION_ANULACIONES",
        "POLIZAS_ALTAS",
        "POLIZAS_ANULADAS",
        "IMPORTE_SINIESTROS",
        "NUM_SINIESTROS",
        "PRIMAS_EMITIDAS",
        "PRIMAS_ANULADAS",
    ]

    for column in numeric_columns:
        if column in ranking.columns:
            ranking[column] = pd.to_numeric(ranking[column], errors="coerce").fillna(0)


    ranking["FACTURACION_NETA"] = ranking["FACTURACION_ALTAS_BRUTAS"] - ranking["FACTURACION_ANULACIONES"]
    ranking["POLIZAS_NETAS"] = ranking["POLIZAS_ALTAS"] - ranking["POLIZAS_ANULADAS"]

    ranking["PRIMA_MEDIA_NETA"] = [
        facturacion / polizas if polizas else 0.0
        for facturacion, polizas in zip(ranking["FACTURACION_NETA"], ranking["POLIZAS_NETAS"])
    ]

    ranking["PRIMAS_NETAS"] = ranking["PRIMAS_EMITIDAS"] - ranking["PRIMAS_ANULADAS"]

    ranking["SINIESTRALIDAD"] = [
        importe_siniestros / primas_netas if primas_netas > 0 else 0.0
        for importe_siniestros, primas_netas in zip(ranking["IMPORTE_SINIESTROS"], ranking["PRIMAS_NETAS"])
    ]

    ranking["CUMPLE_SINIESTRALIDAD"] = ranking["SINIESTRALIDAD"] < SINIESTRALIDAD_MAXIMA

    ranking = ranking[
        [
            "AGENTE", "NOMBRE_AGENCIA", "DEPENDENCIA",
            "FACTURACION_ALTAS_BRUTAS", "FACTURACION_ANULACIONES", "FACTURACION_NETA",
            "PRIMAS_EMITIDAS", "PRIMAS_ANULADAS", "PRIMAS_NETAS",
            "IMPORTE_SINIESTROS", "SINIESTRALIDAD", "CUMPLE_SINIESTRALIDAD",
            "POLIZAS_ALTAS", "POLIZAS_ANULADAS", "POLIZAS_NETAS",
            "NUM_SINIESTROS", "PRIMA_MEDIA_NETA",
        ]
    ].sort_values(
        ["FACTURACION_NETA", "SINIESTRALIDAD", "AGENTE"],
        ascending=[False, True, True],
    )

    ranking.insert(0, "RANKING", range(1, len(ranking) + 1))

    return ranking, altas_detail, anulaciones_detail, siniestros_detail, primas_emitidas_detail, primas_anuladas_detail


def prepare_facturacion_salud_data(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    work["AGENTE"] = work["MEDIADOR"].apply(normalize_agent)
    work["POLIZA_NORMALIZADA"] = work["IDPOLIZA"].apply(lambda value: normalize_text(value, ""))
    work["FECHA_EFECTO_SALUD"] = pd.to_datetime(work["POLIEFEC"], dayfirst=True, errors="coerce")
    work["FECHBAJA_SISTEMA"] = pd.to_datetime(work["FECHBAJA"], dayfirst=True, errors="coerce")
    work["FECHBAJA_ES_1900"] = (
        work["FECHBAJA_SISTEMA"].notna()
        & (work["FECHBAJA_SISTEMA"].dt.date == date(1900, 1, 1))
    )
    work["ANIO_SALUD"] = work["FECHA_EFECTO_SALUD"].dt.year
    work["MES_SALUD"] = work["FECHA_EFECTO_SALUD"].dt.month
    work["PRIMA_NETA_SALUD_VALOR"] = work["PRIMA NETA"].apply(parse_spanish_number)

    return work


def prepare_bajas_salud_data(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    work["POLIZA_NORMALIZADA"] = work["POLIZA"].apply(lambda value: normalize_text(value, ""))
    work["DES_PRODUCTO_NORMALIZADO"] = work["DES_PRODUCTO"].apply(normalize_product)
    work["FECHA_BAJA_SALUD"] = pd.to_datetime(work["FEC_EFECTO_BAJA"], dayfirst=True, errors="coerce")
    work["FECHA_GRABACION_BAJA"] = pd.to_datetime(work["FEC_GRABACION_BAJA"], dayfirst=True, errors="coerce")
    work["FECHA_REACTIVACION_SALUD"] = pd.to_datetime(work["FEC_EFECTO_REACTIV"], dayfirst=True, errors="coerce")
    work["ANIO_BAJA_SALUD"] = work["FECHA_BAJA_SALUD"].dt.year
    work["MES_BAJA_SALUD"] = work["FECHA_BAJA_SALUD"].dt.month
    work["ANIO_GRABACION_BAJA"] = work["FECHA_GRABACION_BAJA"].dt.year
    work["MES_GRABACION_BAJA"] = work["FECHA_GRABACION_BAJA"].dt.month

    return work


def calculate_facturacion_salud(
    facturacion_salud_df: pd.DataFrame,
    bajas_salud_df: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    facturacion_detail = prepare_facturacion_salud_data(facturacion_salud_df)
    bajas_detail = prepare_bajas_salud_data(bajas_salud_df)

    bruta_mask = in_date_range(facturacion_detail["FECHA_EFECTO_SALUD"], fecha_desde, fecha_hasta)
    salud_bruta_detail = facturacion_detail[bruta_mask].copy()

    bajas_mask = (
        in_date_range(bajas_detail["FECHA_GRABACION_BAJA"], fecha_desde, fecha_hasta)
        & bajas_detail["FECHA_REACTIVACION_SALUD"].isna()
        & ~bajas_detail["DES_PRODUCTO_NORMALIZADO"].eq("ASISA VIDA RIESGO")
    )
    bajas_validas = bajas_detail[bajas_mask].copy().drop_duplicates("POLIZA_NORMALIZADA")

    # Anulaciones totales de Salud:
    # cuenta bajas del periodo, aunque la poliza se haya dado de alta antes del periodo.
    salud_anulaciones_detail = pd.merge(
        facturacion_detail,
        bajas_validas,
        on="POLIZA_NORMALIZADA",
        how="inner",
        suffixes=("", "_BAJA"),
    )
    salud_anulaciones_detail = salud_anulaciones_detail[
        salud_anulaciones_detail["FECHBAJA_ES_1900"] != True
    ].copy()

    # NUEVO: anulaciones de nueva produccion de Salud:
    # solo cuenta las bajas de polizas cuya alta/efecto tambien esta dentro del periodo seleccionado.
    salud_anulaciones_np_detail = pd.merge(
        salud_bruta_detail,
        bajas_validas,
        on="POLIZA_NORMALIZADA",
        how="inner",
        suffixes=("", "_BAJA"),
    )
    salud_anulaciones_np_detail = salud_anulaciones_np_detail[
        salud_anulaciones_np_detail["FECHBAJA_ES_1900"] != True
    ].copy()

    salud_bruta = (
        salud_bruta_detail.groupby("AGENTE", dropna=False)
        .agg(
            FACTURACION_SALUD_BRUTA=("PRIMA_NETA_SALUD_VALOR", "sum"),
            POLIZAS_SALUD_BRUTAS=("POLIZA_NORMALIZADA", "nunique"),
        )
        .reset_index()
    )

    salud_anulaciones = (
        salud_anulaciones_detail.groupby("AGENTE", dropna=False)
        .agg(
            FACTURACION_SALUD_ANULACIONES=("PRIMA_NETA_SALUD_VALOR", "sum"),
            POLIZAS_SALUD_ANULADAS=("POLIZA_NORMALIZADA", "nunique"),
        )
        .reset_index()
    )

    salud_anulaciones_np = (
        salud_anulaciones_np_detail.groupby("AGENTE", dropna=False)
        .agg(
            FACTURACION_SALUD_ANULACIONES_NUEVA_PRODUCCION=("PRIMA_NETA_SALUD_VALOR", "sum"),
            POLIZAS_SALUD_ANULADAS_NUEVA_PRODUCCION=("POLIZA_NORMALIZADA", "nunique"),
        )
        .reset_index()
    )

    ranking_salud = pd.merge(salud_bruta, salud_anulaciones, on="AGENTE", how="outer")
    ranking_salud = pd.merge(ranking_salud, salud_anulaciones_np, on="AGENTE", how="outer")

    if ranking_salud.empty:
        return (
            pd.DataFrame(
                columns=[
                    "RANKING_SALUD", "AGENTE",
                    "FACTURACION_SALUD_BRUTA", "FACTURACION_SALUD_ANULACIONES", "FACTURACION_SALUD_NETA",
                    "FACTURACION_SALUD_ANULACIONES_NUEVA_PRODUCCION",
                    "FACTURACION_SALUD_NETA_NUEVA_PRODUCCION",
                    "POLIZAS_SALUD_BRUTAS", "POLIZAS_SALUD_ANULADAS", "POLIZAS_SALUD_NETAS",
                    "POLIZAS_SALUD_ANULADAS_NUEVA_PRODUCCION",
                    "POLIZAS_SALUD_NETAS_NUEVA_PRODUCCION",
                ]
            ),
            salud_bruta_detail,
            salud_anulaciones_detail,
        )

    for column in [
        "FACTURACION_SALUD_BRUTA", "FACTURACION_SALUD_ANULACIONES",
        "FACTURACION_SALUD_ANULACIONES_NUEVA_PRODUCCION",
        "POLIZAS_SALUD_BRUTAS", "POLIZAS_SALUD_ANULADAS",
        "POLIZAS_SALUD_ANULADAS_NUEVA_PRODUCCION",
    ]:
        ranking_salud[column] = ranking_salud[column].fillna(0)

    ranking_salud["FACTURACION_SALUD_NETA"] = ranking_salud["FACTURACION_SALUD_BRUTA"] - ranking_salud["FACTURACION_SALUD_ANULACIONES"]
    ranking_salud["POLIZAS_SALUD_NETAS"] = ranking_salud["POLIZAS_SALUD_BRUTAS"] - ranking_salud["POLIZAS_SALUD_ANULADAS"]

    # NUEVO: neta considerando solo anulaciones de la nueva produccion del periodo.
    ranking_salud["FACTURACION_SALUD_NETA_NUEVA_PRODUCCION"] = (
        ranking_salud["FACTURACION_SALUD_BRUTA"]
        - ranking_salud["FACTURACION_SALUD_ANULACIONES_NUEVA_PRODUCCION"]
    )
    ranking_salud["POLIZAS_SALUD_NETAS_NUEVA_PRODUCCION"] = (
        ranking_salud["POLIZAS_SALUD_BRUTAS"]
        - ranking_salud["POLIZAS_SALUD_ANULADAS_NUEVA_PRODUCCION"]
    )

    ranking_salud = ranking_salud.sort_values(["FACTURACION_SALUD_NETA", "AGENTE"], ascending=[False, True])
    ranking_salud.insert(0, "RANKING_SALUD", range(1, len(ranking_salud) + 1))

    return ranking_salud, salud_bruta_detail, salud_anulaciones_detail


def prepare_facturacion_vida_data(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    work["AGENTE"] = work["CODIMEDI"].apply(normalize_agent)
    work["POLIZA_NORMALIZADA"] = work["NUMERO"].apply(lambda value: normalize_text(value, ""))
    work["FECHA_ALTA_VIDA"] = pd.to_datetime(work["FECHALTA"], dayfirst=True, errors="coerce")
    work["ANIO_VIDA"] = work["FECHA_ALTA_VIDA"].dt.year
    work["MES_VIDA"] = work["FECHA_ALTA_VIDA"].dt.month
    work["PRIMA_VIDA_VALOR"] = work["PRIMATOTAL"].apply(parse_spanish_number)

    return work


def calculate_facturacion_vida(
    facturacion_vida_df: pd.DataFrame,
    bajas_salud_df: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    facturacion_detail = prepare_facturacion_vida_data(facturacion_vida_df)
    bajas_detail = prepare_bajas_salud_data(bajas_salud_df)

    bruta_mask = in_date_range(facturacion_detail["FECHA_ALTA_VIDA"], fecha_desde, fecha_hasta)
    vida_bruta_detail = facturacion_detail[bruta_mask].copy()

    bajas_mask = (
        in_date_range(bajas_detail["FECHA_GRABACION_BAJA"], fecha_desde, fecha_hasta)
        & bajas_detail["FECHA_REACTIVACION_SALUD"].isna()
        & bajas_detail["DES_PRODUCTO_NORMALIZADO"].eq("ASISA VIDA RIESGO")
    )
    bajas_validas = bajas_detail[bajas_mask].copy().drop_duplicates("POLIZA_NORMALIZADA")

    # Anulaciones totales de Vida:
    # cuenta bajas del periodo, aunque la poliza se haya dado de alta antes del periodo.
    vida_anulaciones_detail = pd.merge(
        facturacion_detail,
        bajas_validas,
        on="POLIZA_NORMALIZADA",
        how="inner",
        suffixes=("", "_BAJA"),
    )

    # NUEVO: anulaciones de nueva produccion de Vida:
    # solo cuenta las bajas de polizas cuya alta tambien esta dentro del periodo seleccionado.
    vida_anulaciones_np_detail = pd.merge(
        vida_bruta_detail,
        bajas_validas,
        on="POLIZA_NORMALIZADA",
        how="inner",
        suffixes=("", "_BAJA"),
    )

    vida_bruta = (
        vida_bruta_detail.groupby("AGENTE", dropna=False)
        .agg(
            FACTURACION_VIDA_BRUTA=("PRIMA_VIDA_VALOR", "sum"),
            POLIZAS_VIDA_BRUTAS=("POLIZA_NORMALIZADA", "nunique"),
        )
        .reset_index()
    )

    vida_anulaciones = (
        vida_anulaciones_detail.groupby("AGENTE", dropna=False)
        .agg(
            FACTURACION_VIDA_ANULACIONES=("PRIMA_VIDA_VALOR", "sum"),
            POLIZAS_VIDA_ANULADAS=("POLIZA_NORMALIZADA", "nunique"),
        )
        .reset_index()
    )

    vida_anulaciones_np = (
        vida_anulaciones_np_detail.groupby("AGENTE", dropna=False)
        .agg(
            FACTURACION_VIDA_ANULACIONES_NUEVA_PRODUCCION=("PRIMA_VIDA_VALOR", "sum"),
            POLIZAS_VIDA_ANULADAS_NUEVA_PRODUCCION=("POLIZA_NORMALIZADA", "nunique"),
        )
        .reset_index()
    )

    ranking_vida = pd.merge(vida_bruta, vida_anulaciones, on="AGENTE", how="outer")
    ranking_vida = pd.merge(ranking_vida, vida_anulaciones_np, on="AGENTE", how="outer")

    if ranking_vida.empty:
        return (
            pd.DataFrame(
                columns=[
                    "RANKING_VIDA", "AGENTE",
                    "FACTURACION_VIDA_BRUTA", "FACTURACION_VIDA_ANULACIONES", "FACTURACION_VIDA_NETA",
                    "FACTURACION_VIDA_ANULACIONES_NUEVA_PRODUCCION",
                    "FACTURACION_VIDA_NETA_NUEVA_PRODUCCION",
                    "POLIZAS_VIDA_BRUTAS", "POLIZAS_VIDA_ANULADAS", "POLIZAS_VIDA_NETAS",
                    "POLIZAS_VIDA_ANULADAS_NUEVA_PRODUCCION",
                    "POLIZAS_VIDA_NETAS_NUEVA_PRODUCCION",
                ]
            ),
            vida_bruta_detail,
            vida_anulaciones_detail,
        )

    for column in [
        "FACTURACION_VIDA_BRUTA", "FACTURACION_VIDA_ANULACIONES",
        "FACTURACION_VIDA_ANULACIONES_NUEVA_PRODUCCION",
        "POLIZAS_VIDA_BRUTAS", "POLIZAS_VIDA_ANULADAS",
        "POLIZAS_VIDA_ANULADAS_NUEVA_PRODUCCION",
    ]:
        ranking_vida[column] = ranking_vida[column].fillna(0)

    ranking_vida["FACTURACION_VIDA_NETA"] = ranking_vida["FACTURACION_VIDA_BRUTA"] - ranking_vida["FACTURACION_VIDA_ANULACIONES"]
    ranking_vida["POLIZAS_VIDA_NETAS"] = ranking_vida["POLIZAS_VIDA_BRUTAS"] - ranking_vida["POLIZAS_VIDA_ANULADAS"]

    # NUEVO: neta considerando solo anulaciones de la nueva produccion del periodo.
    ranking_vida["FACTURACION_VIDA_NETA_NUEVA_PRODUCCION"] = (
        ranking_vida["FACTURACION_VIDA_BRUTA"]
        - ranking_vida["FACTURACION_VIDA_ANULACIONES_NUEVA_PRODUCCION"]
    )
    ranking_vida["POLIZAS_VIDA_NETAS_NUEVA_PRODUCCION"] = (
        ranking_vida["POLIZAS_VIDA_BRUTAS"]
        - ranking_vida["POLIZAS_VIDA_ANULADAS_NUEVA_PRODUCCION"]
    )

    ranking_vida = ranking_vida.sort_values(["FACTURACION_VIDA_NETA", "AGENTE"], ascending=[False, True])
    ranking_vida.insert(0, "RANKING_VIDA", range(1, len(ranking_vida) + 1))

    return ranking_vida, vida_bruta_detail, vida_anulaciones_detail


# ============================================================
# CLASIFICACIONES Y TOP RANKINGS
# ============================================================

def get_liga_decesos(codimedi: object) -> str:
    code = normalize_code_for_liga(codimedi)
    return "LIGA ELITE" if code in LIGA_ELITE_CODES_2025 else "LIGA PRO"


def get_objetivo_decesos(codimedi: object) -> float:
    return DECESOS_OBJETIVO_ELITE if get_liga_decesos(codimedi) == "LIGA ELITE" else DECESOS_OBJETIVO_PRO


def classify_salud(facturacion_salud: float, facturacion_decesos: float) -> str:
    if facturacion_salud >= SALUD_PLAZA_2_MINIMA and facturacion_decesos >= SALUD_PLAZA_2_DECESOS_MINIMA:
        return "2 PLAZAS DOBLES"

    if facturacion_salud >= SALUD_PLAZA_1_MINIMA and facturacion_decesos >= SALUD_PLAZA_1_DECESOS_MINIMA:
        return "1 PLAZA DOBLE"

    return "No clasifica"


def get_objetivo_salud(facturacion_decesos: float) -> float:
    # Si ya cumple el minimo de Decesos para la opcion 2, se mide contra 80k Salud.
    # Si no, se mide contra 25k Salud para opcion 1.
    if facturacion_decesos >= SALUD_PLAZA_2_DECESOS_MINIMA:
        return SALUD_PLAZA_2_MINIMA
    return SALUD_PLAZA_1_MINIMA


def get_objetivo_decesos_salud(facturacion_decesos: float) -> float:
    if facturacion_decesos >= SALUD_PLAZA_2_DECESOS_MINIMA:
        return SALUD_PLAZA_2_DECESOS_MINIMA
    return SALUD_PLAZA_1_DECESOS_MINIMA


def classify_vida(facturacion_vida: float, facturacion_decesos: float) -> str:
    if facturacion_vida >= VIDA_PLAZA_DOBLE_MINIMA:
        return "PLAZA DOBLE"

    if facturacion_vida >= VIDA_PLAZA_DOBLE_CON_DECESOS_MINIMA and facturacion_decesos >= VIDA_DECESOS_MINIMA:
        return "PLAZA DOBLE"

    return "No clasifica"


def get_objetivo_vida(facturacion_decesos: float) -> float:
    if facturacion_decesos >= VIDA_DECESOS_MINIMA:
        return VIDA_PLAZA_DOBLE_CON_DECESOS_MINIMA
    return VIDA_PLAZA_DOBLE_MINIMA


def get_objetivo_decesos_vida(facturacion_decesos: float) -> float:
    if facturacion_decesos >= VIDA_DECESOS_MINIMA:
        return VIDA_DECESOS_MINIMA
    return 0.0


def build_ranking_decesos_top10(ranking: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "PUESTO_LIGA", "LIGA_DECESOS", "CODIMEDI","POBLACION", "NOMBRE_AGENCIA", "RESPONSABLE",
        "FACTURACION_NETA", "OBJETIVO_DECESOS", "PORCENTAJE_OBJETIVO_DECESOS",
        "SINIESTRALIDAD", "CUMPLE_SINIESTRALIDAD",
        "IMPORTE_SINIESTROS", "PRIMAS_NETAS",
    ]

    if ranking.empty:
        return pd.DataFrame(columns=columns)

    result = ranking.copy()

    result["LIGA_DECESOS"] = result["CODIMEDI"].apply(get_liga_decesos)
    result["OBJETIVO_DECESOS"] = result["CODIMEDI"].apply(get_objetivo_decesos)
    result["PORCENTAJE_OBJETIVO_DECESOS"] = [
        calculate_progress(facturacion, objetivo)
        for facturacion, objetivo in zip(result["FACTURACION_NETA"], result["OBJETIVO_DECESOS"])
    ]

    result["ORDEN_LIGA"] = result["LIGA_DECESOS"].map({"LIGA ELITE": 1, "LIGA PRO": 2})

    result = result.sort_values(
        ["ORDEN_LIGA", "FACTURACION_NETA", "SINIESTRALIDAD", "CODIMEDI"],
        ascending=[True, False, True, True],
    )

    result["PUESTO_LIGA"] = result.groupby("LIGA_DECESOS").cumcount().add(1)
    result = result.drop(columns=["ORDEN_LIGA"])

    return result[columns]


def build_ranking_salud_top10(ranking_salud: pd.DataFrame, ranking_decesos: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "PUESTO_SALUD", "CLASIFICACION_SALUD", "POBLACION", "CODIMEDI", "NOMBRE_AGENCIA", "RESPONSABLE",
        "FACTURACION_SALUD_NETA", "FACTURACION_SALUD_NETA_NUEVA_PRODUCCION",
        "FACTURACION_SALUD_ANULACIONES_NUEVA_PRODUCCION",
        "POLIZAS_SALUD_ANULADAS_NUEVA_PRODUCCION",
        "FACTURACION_DECESOS_NETA",
        "OBJETIVO_SALUD", "PORCENTAJE_OBJETIVO_SALUD",
        "OBJETIVO_DECESOS_SALUD", "PORCENTAJE_OBJETIVO_DECESOS_SALUD",
    ]

    if ranking_salud.empty:
        return pd.DataFrame(columns=columns)

    salud_columns = [
        "AGENTE", "CODIMEDI", "POBLACION", "NOMBRE_AGENCIA", "RESPONSABLE",
        "FACTURACION_SALUD_NETA", "FACTURACION_SALUD_NETA_NUEVA_PRODUCCION",
        "FACTURACION_SALUD_ANULACIONES_NUEVA_PRODUCCION",
        "POLIZAS_SALUD_ANULADAS_NUEVA_PRODUCCION",
    ]
    salud = ranking_salud[[column for column in salud_columns if column in ranking_salud.columns]].copy()

    if "CODIMEDI" not in salud.columns:
        salud["CODIMEDI"] = salud["AGENTE"]
    if "NOMBRE_AGENCIA" not in salud.columns:
        salud["NOMBRE_AGENCIA"] = salud["AGENTE"]
    if "RESPONSABLE" not in salud.columns:
        salud["RESPONSABLE"] = "Sin responsable"
    if "POBLACION" not in salud.columns:
        salud["POBLACION"] = "Sin población"

    if ranking_decesos.empty:
        decesos = pd.DataFrame(columns=["AGENTE", "FACTURACION_DECESOS_NETA"])
    else:
        decesos = ranking_decesos[["AGENTE", "FACTURACION_NETA"]].rename(
            columns={"FACTURACION_NETA": "FACTURACION_DECESOS_NETA"}
        )

    result = pd.merge(salud, decesos, on="AGENTE", how="left")
    result["FACTURACION_DECESOS_NETA"] = result["FACTURACION_DECESOS_NETA"].fillna(0)

    result["CLASIFICACION_SALUD"] = [
        classify_salud(salud_neta, decesos_neta)
        for salud_neta, decesos_neta in zip(result["FACTURACION_SALUD_NETA"], result["FACTURACION_DECESOS_NETA"])
    ]
    result["OBJETIVO_SALUD"] = result["FACTURACION_DECESOS_NETA"].apply(get_objetivo_salud)
    result["PORCENTAJE_OBJETIVO_SALUD"] = [
        calculate_progress(salud_neta, objetivo)
        for salud_neta, objetivo in zip(result["FACTURACION_SALUD_NETA"], result["OBJETIVO_SALUD"])
    ]
    result["OBJETIVO_DECESOS_SALUD"] = result["FACTURACION_DECESOS_NETA"].apply(get_objetivo_decesos_salud)
    result["PORCENTAJE_OBJETIVO_DECESOS_SALUD"] = [
        calculate_progress(decesos_neta, objetivo)
        for decesos_neta, objetivo in zip(result["FACTURACION_DECESOS_NETA"], result["OBJETIVO_DECESOS_SALUD"])
    ]

    result = result.sort_values(
        ["FACTURACION_SALUD_NETA", "FACTURACION_DECESOS_NETA", "CODIMEDI"],
        ascending=[False, False, True],
    ).head(10)

    result.insert(0, "PUESTO_SALUD", range(1, len(result) + 1))

    return result[columns]


def build_ranking_vida_top10(ranking_vida: pd.DataFrame, ranking_decesos: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = [
        "PUESTO_VIDA", "CLASIFICACION_VIDA", "POBLACION", "CODIMEDI", "NOMBRE_AGENCIA", "RESPONSABLE",
        "FACTURACION_VIDA_NETA", "FACTURACION_VIDA_NETA_NUEVA_PRODUCCION",
        "FACTURACION_VIDA_ANULACIONES_NUEVA_PRODUCCION",
        "POLIZAS_VIDA_ANULADAS_NUEVA_PRODUCCION",
        "FACTURACION_DECESOS_NETA",
        "OBJETIVO_VIDA", "PORCENTAJE_OBJETIVO_VIDA",
        "OBJETIVO_DECESOS_VIDA", "PORCENTAJE_OBJETIVO_DECESOS_VIDA",
        "FACTURACION_VIDA_BRUTA", "FACTURACION_VIDA_ANULACIONES", "POLIZAS_VIDA_NETAS",
    ]

    if ranking_vida.empty:
        return pd.DataFrame(columns=columns)

    result = ranking_vida.copy()

    if "CODIMEDI" not in result.columns:
        result["CODIMEDI"] = result["AGENTE"]
    if "NOMBRE_AGENCIA" not in result.columns:
        result["NOMBRE_AGENCIA"] = result["AGENTE"]
    if "RESPONSABLE" not in result.columns:
        result["RESPONSABLE"] = "Sin responsable"
    if "POBLACION" not in result.columns:
        result["POBLACION"] = "Sin población"

    if ranking_decesos is None or ranking_decesos.empty:
        result["FACTURACION_DECESOS_NETA"] = 0.0
    else:
        decesos = ranking_decesos[["AGENTE", "FACTURACION_NETA"]].rename(
            columns={"FACTURACION_NETA": "FACTURACION_DECESOS_NETA"}
        )
        result = pd.merge(result, decesos, on="AGENTE", how="left")
        result["FACTURACION_DECESOS_NETA"] = result["FACTURACION_DECESOS_NETA"].fillna(0)

    result["CLASIFICACION_VIDA"] = [
        classify_vida(vida_neta, decesos_neta)
        for vida_neta, decesos_neta in zip(result["FACTURACION_VIDA_NETA"], result["FACTURACION_DECESOS_NETA"])
    ]
    result["OBJETIVO_VIDA"] = result["FACTURACION_DECESOS_NETA"].apply(get_objetivo_vida)
    result["PORCENTAJE_OBJETIVO_VIDA"] = [
        calculate_progress(vida_neta, objetivo)
        for vida_neta, objetivo in zip(result["FACTURACION_VIDA_NETA"], result["OBJETIVO_VIDA"])
    ]
    result["OBJETIVO_DECESOS_VIDA"] = result["FACTURACION_DECESOS_NETA"].apply(get_objetivo_decesos_vida)
    result["PORCENTAJE_OBJETIVO_DECESOS_VIDA"] = [
        calculate_progress(decesos_neta, objetivo) if objetivo > 0 else 0.0
        for decesos_neta, objetivo in zip(result["FACTURACION_DECESOS_NETA"], result["OBJETIVO_DECESOS_VIDA"])
    ]

    result = result.sort_values(
        ["FACTURACION_VIDA_NETA", "FACTURACION_DECESOS_NETA", "CODIMEDI"],
        ascending=[False, False, True],
    ).head(10)

    result.insert(0, "PUESTO_VIDA", range(1, len(result) + 1))

    return result[columns]


def build_sheet_summary(df: pd.DataFrame, file_name: str) -> pd.DataFrame:
    if "HOJA_ORIGEN" not in df.columns:
        return pd.DataFrame(columns=["TIPO_ARCHIVO", "ARCHIVO", "HOJA", "FILAS_LEIDAS"])

    group_columns = ["HOJA_ORIGEN"]
    if "ARCHIVO_ORIGEN" in df.columns:
        group_columns = ["ARCHIVO_ORIGEN", "HOJA_ORIGEN"]

    summary = (
        df.groupby(group_columns, dropna=False)
        .size()
        .reset_index(name="FILAS_LEIDAS")
        .rename(columns={"ARCHIVO_ORIGEN": "ARCHIVO", "HOJA_ORIGEN": "HOJA"})
    )

    if "ARCHIVO" not in summary.columns:
        summary.insert(0, "ARCHIVO", file_name)

    summary.insert(0, "TIPO_ARCHIVO", file_name)

    return summary


def format_euro(value: float) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def format_percent(value: float) -> str:
    return f"{value:.2%}".replace(".", ",")


def detail_columns_for_display(detail: pd.DataFrame) -> list[str]:
    columns = [
        "HOJA_ORIGEN", "MOVIMIENTO", "PRODUCTO", "POLIALTA", "FECHA BAJA",
        "FECHA EMISION", "FECHA GRABACION", "CAUSA", "MOTIVO", "POLIZA",
        "MEDIADOR", "SECTOCOB", "SECTOR", "NOMBRE_AGENCIA", "DEPENDENCIA",
        "PRIMA NETA", "PRIMA_NETA_VALOR", "FECHA_MOVIMIENTO",
        "ANIO_MOVIMIENTO", "MES_MOVIMIENTO",
    ]
    return [column for column in columns if column in detail.columns]


def siniestros_columns_for_display(detail: pd.DataFrame) -> list[str]:
    columns = [
        "HOJA_ORIGEN", "PRODUCTO", "CODIMEDI", "AGENTE", "FECHOCUR",
        "FECHA_SINIESTRO", "ANIO_SINIESTRO", "MES_SINIESTRO", "NUMESINI",
        "POLIZSEC", "ESTADO", "MOTIVO", "COBERTURA", "NATURALEZA",
        "RESERACT", "RESERACT_VALOR", "EXPECACT", "EXPECACT_VALOR",
        "PAGOSPDT", "PAGOSPDT_VALOR", "PAGOSRZD", "PAGOSRZD_VALOR",
        "COSTESIN", "COSTESIN_VALOR", "IMPORTE_SINIESTRO",
    ]
    return [column for column in columns if column in detail.columns]


def primas_columns_for_display(detail: pd.DataFrame) -> list[str]:
    columns = [
        "ARCHIVO_ORIGEN", "HOJA_ORIGEN", "MOVIMIENTO_PRIMA", "MEDIADOR",
        "AGENTE", "GARANTIA", "POLIPTOT", "POLIPNET", "POLIPNET_VALOR",
        "CONSORCIO", "CLEA", "IPS", "RECARGO",
    ]
    return [column for column in columns if column in detail.columns]


def salud_columns_for_display(detail: pd.DataFrame) -> list[str]:
    columns = [
        "ARCHIVO_ORIGEN", "HOJA_ORIGEN", "PRODUCTO", "IDPOLIZA",
        "POLIZA_NORMALIZADA", "MEDIADOR", "AGENTE", "POLIEFEC",
        "FECHA_EFECTO_SALUD", "PRIMA NETA", "PRIMA_NETA_SALUD_VALOR",
        "DES_PRODUCTO", "FEC_EFECTO_BAJA", "FEC_GRABACION_BAJA", "FEC_EFECTO_REACTIV",
        "MOTIVO_BAJA", "TOMADOR", "NIF",
    ]
    return [column for column in columns if column in detail.columns]


def vida_columns_for_display(detail: pd.DataFrame) -> list[str]:
    columns = [
        "ARCHIVO_ORIGEN", "HOJA_ORIGEN", "NUMERO", "POLIZA_NORMALIZADA",
        "CODIMEDI", "AGENTE", "ESTADO", "FECHALTA", "FECHA_ALTA_VIDA",
        "GARANTIA", "PRIMATOTAL", "PRIMA_VIDA_VALOR", "NOMBRE", "APE1",
        "APE2", "NUMEDOCU", "DES_PRODUCTO", "FEC_EFECTO_BAJA",
        "FEC_GRABACION_BAJA", "FEC_EFECTO_REACTIV", "MOTIVO_BAJA",
    ]
    return [column for column in columns if column in detail.columns]


def dataframe_to_excel(
    ranking: pd.DataFrame,
    ranking_salud: pd.DataFrame,
    ranking_vida: pd.DataFrame,
    ranking_asesor_decesos: pd.DataFrame,
    ranking_decesos_top10: pd.DataFrame,
    ranking_salud_top10: pd.DataFrame,
    ranking_vida_top10: pd.DataFrame,
    ranking_asesor_decesos_top10: pd.DataFrame,
    altas_detail: pd.DataFrame,
    anulaciones_detail: pd.DataFrame,
    altas_asesor_detail: pd.DataFrame,
    anulaciones_asesor_detail: pd.DataFrame,
    siniestros_detail: pd.DataFrame,
    primas_emitidas_detail: pd.DataFrame,
    primas_anuladas_detail: pd.DataFrame,
    salud_bruta_detail: pd.DataFrame,
    salud_anulaciones_detail: pd.DataFrame,
    vida_bruta_detail: pd.DataFrame,
    vida_anulaciones_detail: pd.DataFrame,
    sheet_summary: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
    excluded_products: list[str],
) -> bytes:
    output = BytesIO()

    parametros = pd.DataFrame(
        [
            {"CAMPO": "FECHA_DESDE", "VALOR": fecha_desde.strftime("%d/%m/%Y")},
            {"CAMPO": "FECHA_HASTA", "VALOR": fecha_hasta.strftime("%d/%m/%Y")},
            {"CAMPO": "PRODUCTOS_EXCLUIDOS", "VALOR": ", ".join(excluded_products)},
            {"CAMPO": "PERIODO", "VALOR": "Se filtran movimientos entre FECHA_DESDE y FECHA_HASTA, ambas incluidas"},
            {"CAMPO": "SINIESTROS_FECHA", "VALOR": "FECHOCUR"},
            {"CAMPO": "SINIESTROS_IMPORTE", "VALOR": "RESERACT + PAGOSPDT"},
            {"CAMPO": "DECESOS_LIGA_PRO", "VALOR": "Mediadores no Elite 2025. Objetivo 2026: 30.000 euros en Decesos"},
            {"CAMPO": "DECESOS_LIGA_ELITE", "VALOR": "Codigos 46407, 28005, 34400 y 100. Objetivo 2026: 60.000 euros en Decesos"},
            {"CAMPO": "SALUD_OPCION_1", "VALOR": "1 plaza doble: 25.000 euros Salud + 12.000 euros Decesos"},
            {"CAMPO": "SALUD_OPCION_2", "VALOR": "2 plazas dobles: 80.000 euros Salud + 4.000 euros Decesos"},
            {"CAMPO": "VIDA_OPCION_1", "VALOR": "Plaza doble: 10.000 euros Vida"},
            {"CAMPO": "VIDA_OPCION_2", "VALOR": "Plaza doble: 5.000 euros Vida + 5.000 euros Decesos"},
            {"CAMPO": "SALUD_BRUTA", "VALOR": "FACTURACION_SALUD con POLIEFEC dentro del periodo"},
            {"CAMPO": "SALUD_ANULACIONES", "VALOR": "INFORME_BAJAS_SALUD con FEC_GRABACION_BAJA dentro del periodo, sin FEC_EFECTO_REACTIV, excluyendo ASISA VIDA RIESGO y descartando FECHBAJA=01/01/1900 en FACTURACION_SALUD"},
            {"CAMPO": "VIDA_BRUTA", "VALOR": "FACTURACION_VIDA con FECHALTA dentro del periodo y PRIMATOTAL como importe"},
            {"CAMPO": "VIDA_ANULACIONES", "VALOR": "INFORME_BAJAS_SALUD con FEC_GRABACION_BAJA dentro del periodo, sin FEC_EFECTO_REACTIV y DES_PRODUCTO = ASISA VIDA RIESGO. Suma PRIMATOTAL de todas las garantias de la poliza en FACTURACION_VIDA"},
            {"CAMPO": "TOP_RANKINGS", "VALOR": "Se muestran hasta 10 puestos por facturacion neta"},
            {"CAMPO": "RANKING_ASESORES","VALOR": "El ranking de asesores usa FACTURACION_DECESOS_ASESOR agrupando por CODIGO_RED_COMERCIAL y COMERCIAL. Las anulaciones se cruzan por POLIZA y solo cuentan si la poliza tiene POLIALTA del mismo año.",
            },
        ]
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        parametros.to_excel(writer, index=False, sheet_name="PARAMETROS")
        sheet_summary.to_excel(writer, index=False, sheet_name="COMPROBACION_HOJAS")
        ranking_decesos_top10.to_excel(writer, index=False, sheet_name="RANKING_DECESOS")
        ranking_salud_top10.to_excel(writer, index=False, sheet_name="RANKING_SALUD")
        ranking_vida_top10.to_excel(writer, index=False, sheet_name="RANKING_VIDA")
        ranking_asesor_decesos_top10.to_excel(writer, index=False, sheet_name="RANKING_ASESOR_DEC")
        ranking.to_excel(writer, index=False, sheet_name="RANKING_NETO_DECESOS")
        ranking_asesor_decesos.to_excel(writer, index=False, sheet_name="RANKING_ASESOR_DEC_FULL")
        ranking_salud.to_excel(writer, index=False, sheet_name="FACTURACION_SALUD")
        ranking_vida.to_excel(writer, index=False, sheet_name="FACTURACION_VIDA")
        altas_detail[detail_columns_for_display(altas_detail)].to_excel(writer, index=False, sheet_name="DETALLE_ALTAS_DECESOS")
        anulaciones_detail[detail_columns_for_display(anulaciones_detail)].to_excel(writer, index=False, sheet_name="DETALLE_ANUL_DECESOS")
        altas_asesor_detail.to_excel(writer, index=False, sheet_name="DETALLE_ALTAS_ASESOR")
        anulaciones_asesor_detail.to_excel(writer, index=False, sheet_name="DETALLE_ANUL_ASESOR")
        siniestros_detail[siniestros_columns_for_display(siniestros_detail)].to_excel(writer, index=False, sheet_name="DETALLE_SINIESTROS")
        primas_emitidas_detail[primas_columns_for_display(primas_emitidas_detail)].to_excel(writer, index=False, sheet_name="DETALLE_PRIMAS_EMIT")
        primas_anuladas_detail[primas_columns_for_display(primas_anuladas_detail)].to_excel(writer, index=False, sheet_name="DETALLE_PRIMAS_ANUL")
        salud_bruta_detail[salud_columns_for_display(salud_bruta_detail)].to_excel(writer, index=False, sheet_name="DETALLE_SALUD_BRUTA")
        salud_anulaciones_detail[salud_columns_for_display(salud_anulaciones_detail)].to_excel(writer, index=False, sheet_name="DETALLE_SALUD_ANUL")
        vida_bruta_detail[vida_columns_for_display(vida_bruta_detail)].to_excel(writer, index=False, sheet_name="DETALLE_VIDA_BRUTA")
        vida_anulaciones_detail[vida_columns_for_display(vida_anulaciones_detail)].to_excel(writer, index=False, sheet_name="DETALLE_VIDA_ANUL")

    return output.getvalue()
