"""RN-02 / CU-11: MotorReincidencia (actor Sistema)."""
import pandas as pd
from sqlalchemy import text

from . import parametros
from .db import alertas, engine

DIAS_POR_MES = 30.4375


def detectar(eventos: pd.DataFrame, umbral: int, ventana_meses: int) -> pd.DataFrame:
    """eventos: tipo_documento, documento, fecha. Marca pacientes con >= umbral eventos
    dentro de cualquier ventana movil de `ventana_meses`."""
    cols = ["tipo_documento", "documento", "n_eventos", "fecha_inicio", "fecha_fin", "nivel_riesgo"]
    if eventos.empty:
        return pd.DataFrame(columns=cols)
    ev = eventos.sort_values(["documento", "fecha"]).reset_index(drop=True)
    ventana = pd.Timedelta(days=round(ventana_meses * DIAS_POR_MES))
    previo = ev.groupby("documento")["fecha"].shift(umbral - 1)
    flag = previo.notna() & ((ev["fecha"] - previo) <= ventana)
    if not flag.any():
        return pd.DataFrame(columns=cols)
    hit = ev.loc[flag].assign(fecha_inicio=previo[flag])
    ultimo = hit.groupby("documento").tail(1)  # ultima ventana que cumple
    total = ev.groupby("documento").size().rename("n_eventos")
    out = ultimo.join(total, on="documento").rename(columns={"fecha": "fecha_fin"})
    out["nivel_riesgo"] = (out["n_eventos"] >= 2 * umbral).map({True: "ALTO", False: "MEDIO"})
    return out[cols].reset_index(drop=True)


def _eventos(conn, filtro_sql: str, umbral: int) -> pd.DataFrame:
    sql = f"""SELECT tipo_documento, documento, fecha_ingreso AS fecha FROM atenciones
              WHERE {filtro_sql} AND documento IN (
                  SELECT documento FROM atenciones WHERE {filtro_sql}
                  GROUP BY documento HAVING COUNT(*) >= :u)"""
    df = pd.read_sql(text(sql), conn, params={"u": umbral})
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def recalcular_alertas() -> dict:
    """Recalcula la tabla de alertas con los parametros vigentes. Devuelve conteos por criterio."""
    umbral, ventana = parametros.umbral_y_ventana()
    with engine.begin() as conn:
        conn.execute(alertas.delete())
        resumen = {}
        reglas = {
            "INASISTENCIA": "asistio = 0 AND COALESCE(justificada, 0) = 0",   # RN-02
            "FRECUENCIA": "1 = 1",                                           # >= umbral atenciones
        }
        for criterio, filtro in reglas.items():
            res = detectar(_eventos(conn, filtro, umbral), umbral, ventana)
            resumen[criterio] = len(res)
            if len(res):
                res = res.assign(criterio=criterio)
                res.to_sql("alertas_reincidencia", conn, if_exists="append", index=False, chunksize=5000)
    return resumen


def listar_alertas(criterio: str) -> pd.DataFrame:
    with engine.connect() as c:
        df = pd.read_sql(text("""SELECT tipo_documento, documento, n_eventos, fecha_inicio, fecha_fin, nivel_riesgo
                                 FROM alertas_reincidencia WHERE criterio = :c
                                 ORDER BY n_eventos DESC, fecha_fin DESC"""), c, params={"c": criterio})
    return df
