"""RF-11 / RNF-05: registro e historial de auditoria."""
import pandas as pd
from sqlalchemy import insert, text

from .db import auditoria, engine


def registrar(id_usuario, accion: str, detalle: str = ""):
    with engine.begin() as conn:
        conn.execute(insert(auditoria).values(id_usuario=id_usuario, accion=accion, detalle=detalle[:2000]))


def listar(limite: int = 500, accion: str | None = None) -> pd.DataFrame:
    sql = """SELECT a.fecha, COALESCE(u.correo, 'sistema') AS usuario, a.accion, a.detalle
             FROM auditoria a LEFT JOIN usuarios u ON u.id = a.id_usuario"""
    params = {"lim": limite}
    if accion:
        sql += " WHERE a.accion = :accion"
        params["accion"] = accion
    sql += " ORDER BY a.id DESC LIMIT :lim"
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def acciones_distintas() -> list[str]:
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text("SELECT DISTINCT accion FROM auditoria ORDER BY 1"))]
