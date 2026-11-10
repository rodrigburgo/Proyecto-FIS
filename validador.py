"""RN-01 / RF-03: validacion del archivo (ValidadorArchivo) y limpieza fila a fila."""
import re
import unicodedata

import numpy as np
import pandas as pd

# nombre canonico -> alias aceptados (ya normalizados: minusculas, sin tildes ni simbolos)
ALIAS = {
    "tipo_documento": ["tipodocumento", "tipodoc", "tipoid"],
    "documento": ["documento", "iddelpaciente", "idpaciente", "identificacion", "cedula", "numerodocumento"],
    "edad": ["edad"],
    "ciudad": ["ciudad", "municipio"],
    "centro": ["centroatencion", "centro", "ips", "sede"],
    "especialidad": ["especialidad"],
    "remitido": ["remitidoaotraespecialidad", "remitido", "remision"],
    "ha_venido_antes": ["havenidoantes", "reincidente", "havisitadoantes"],
    "diagnostico": ["diagnostico"],
    "sexo": ["sexo", "genero"],
    "triage": ["niveldetriage", "triage"],
    "estado_paciente": ["estadodelpaciente", "estadopaciente"],
    "medicamento": ["medicamentorecetado", "medicamento"],
    "satisfaccion": ["niveldesatisfaccion", "satisfaccion"],
    "fecha_ingreso": ["fechadeingreso", "fecha", "fechaingreso", "fechacita"],
    "estado_cita": ["estadodelacita", "estadocita", "asistencia"],      # opcional (ausentismo)
    "justificada": ["justificada", "inasistenciajustificada"],           # opcional
}
# RN-01 (adaptada a la base real): columnas sin las cuales no se acepta el archivo
OBLIGATORIAS = ["documento", "edad", "especialidad", "fecha_ingreso", "ha_venido_antes"]
NOMBRES_LEGIBLES = {
    "documento": "Documento", "edad": "Edad", "especialidad": "Especialidad",
    "fecha_ingreso": "Fecha de Ingreso", "ha_venido_antes": "Ha venido antes",
    "tipo_documento": "Tipo Documento", "ciudad": "Ciudad", "centro": "Centro Atención",
    "remitido": "Remitido a otra especialidad", "diagnostico": "Diagnóstico", "sexo": "Sexo",
    "triage": "Nivel de Triage", "estado_paciente": "Estado del Paciente",
    "medicamento": "Medicamento Recetado", "satisfaccion": "Nivel de Satisfacción",
    "estado_cita": "Estado de la cita", "justificada": "Justificada",
}
BINS = [-1, 11, 17, 29, 44, 59, 74, 200]
ETIQUETAS_EDAD = ["0-11", "12-17", "18-29", "30-44", "45-59", "60-74", "75+"]
_SI_NO = {"si": 1, "s": 1, "1": 1, "true": 1, "yes": 1, "no": 0, "n": 0, "0": 0, "false": 0}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra las columnas del archivo a los nombres canonicos."""
    mapa = {}
    for col in df.columns:
        n = _norm(col)
        for canon, alias in ALIAS.items():
            if n in alias and canon not in mapa.values():
                mapa[col] = canon
                break
    return df.rename(columns=mapa)


def validar_columnas(df: pd.DataFrame):
    """-> (ok, faltantes_legibles)"""
    faltan = [NOMBRES_LEGIBLES[c] for c in OBLIGATORIAS if c not in df.columns]
    return len(faltan) == 0, faltan


def _parsear_fechas(serie: pd.Series) -> pd.Series:
    """Camino rapido (ISO); lo que no se pueda se reintenta con formatos mixtos y dia primero (dd/mm/aaaa)."""
    f = pd.to_datetime(serie, errors="coerce")
    falla = f.isna() & serie.notna()
    if falla.any():
        f.loc[falla] = pd.to_datetime(serie[falla], errors="coerce", format="mixed", dayfirst=True)
    return f


def _si_no(serie: pd.Series) -> pd.Series:
    return serie.astype("string").map(lambda x: _SI_NO.get(_norm(x)) if pd.notna(x) else None).astype("Float64")


def _texto(df, col, defecto="Sin dato") -> pd.Series:
    if col not in df.columns:
        return pd.Series(defecto, index=df.index)
    s = df[col].astype("string").str.strip()
    return s.where(s.notna() & (s != "") & (s.str.lower() != "nan"), defecto)


def validar_filas(df: pd.DataFrame):
    """Recibe un bloque con columnas canonicas. -> (df_ok listo para la BD, df_err con 'motivo')."""
    df = df.copy()
    motivos = pd.Series("", index=df.index, dtype=object)

    def marcar(mask, msg):
        mask = mask.fillna(True) if hasattr(mask, "fillna") else mask
        motivos.loc[mask] = motivos.loc[mask] + msg + "; "

    doc = pd.to_numeric(df["documento"], errors="coerce")
    marcar(doc.isna() | (doc <= 0), "Documento inválido")
    edad = pd.to_numeric(df["edad"], errors="coerce")
    marcar(edad.isna() | (edad < 0) | (edad > 120), "Edad inválida (0-120)")
    fecha = _parsear_fechas(df["fecha_ingreso"])
    marcar(fecha.isna(), "Fecha de ingreso inválida")
    esp = _texto(df, "especialidad", "")
    marcar(esp == "", "Especialidad vacía")
    venido = _si_no(df["ha_venido_antes"])
    marcar(venido.isna(), "'Ha venido antes' debe ser Sí/No")

    if "remitido" in df.columns:
        remitido = _si_no(df["remitido"])
        marcar(remitido.isna(), "'Remitido' debe ser Sí/No")
    else:
        remitido = pd.Series(0.0, index=df.index)

    if "estado_cita" in df.columns:
        txt = df["estado_cita"].astype("string").map(lambda x: _norm(x) if pd.notna(x) else "")
        asistio = pd.Series(np.nan, index=df.index)
        falto = txt.str.contains("falt|noasist|inasist", regex=True)
        asistio[txt.str.contains("asisti|atendid", regex=True) & ~falto] = 1
        asistio[falto] = 0
        marcar(asistio.isna(), "Estado de la cita no reconocido (Asistió/Faltó)")
    else:
        asistio = pd.Series(np.nan, index=df.index)
    if "justificada" in df.columns:
        just = _si_no(df["justificada"]).fillna(0)
    else:
        just = pd.Series(np.where(asistio == 0, 0, np.nan), index=df.index)

    sat = pd.to_numeric(_texto(df, "satisfaccion", "").str.extract(r"(\d)")[0], errors="coerce")

    limpio = pd.DataFrame({
        "tipo_documento": _texto(df, "tipo_documento", "CC"),
        "documento": doc, "edad": edad,
        "rango_edad": pd.cut(edad, bins=BINS, labels=ETIQUETAS_EDAD).astype("string"),
        "ciudad": _texto(df, "ciudad"), "centro": _texto(df, "centro"), "especialidad": esp,
        "remitido": remitido, "ha_venido_antes": venido,
        "diagnostico": _texto(df, "diagnostico"), "sexo": _texto(df, "sexo"),
        "triage": _texto(df, "triage"), "estado_paciente": _texto(df, "estado_paciente"),
        "medicamento": _texto(df, "medicamento"), "satisfaccion": sat,
        "fecha_ingreso": fecha, "mes": fecha.dt.strftime("%Y-%m"),
        "asistio": asistio, "justificada": just,
    }, index=df.index)

    malo = motivos != ""
    ok = limpio.loc[~malo].copy()
    for c in ["documento", "edad", "remitido", "ha_venido_antes", "satisfaccion", "asistio", "justificada"]:
        ok[c] = ok[c].astype("Int64")
    err = df.loc[malo].copy()
    err["motivo"] = motivos[malo].str.rstrip("; ")
    return ok, err
