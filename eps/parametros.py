"""RF-05 / CU-07: parametros configurables de las metricas."""
from sqlalchemy import select

from .config import PARAMETROS_DEFECTO
from .db import engine, parametros


def obtener() -> dict:
    with engine.connect() as c:
        d = {r.clave: r.valor for r in c.execute(select(parametros))}
    return {**PARAMETROS_DEFECTO, **d}


def umbral_y_ventana() -> tuple[int, int]:
    p = obtener()
    return int(p["umbral_reincidencia"]), int(p["ventana_meses"])


def guardar(umbral: int, ventana_meses: int):
    with engine.begin() as c:
        for k, v in (("umbral_reincidencia", umbral), ("ventana_meses", ventana_meses)):
            c.execute(parametros.delete().where(parametros.c.clave == k))
            c.execute(parametros.insert().values(clave=k, valor=str(v)))
