"""CitaRepository: consultas agregadas en SQL (escala a millones de filas sin cargar todo en memoria)."""
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy import text

from .db import engine

CAMPOS = {"especialidad": "especialidad", "rango_edad": "rango_edad", "ciudad": "ciudad", "centro": "centro",
          "mes": "mes", "triage": "triage", "estado_paciente": "estado_paciente", "sexo": "sexo",
          "diagnostico": "diagnostico", "satisfaccion": "satisfaccion", "tipo_documento": "tipo_documento"}


@dataclass(frozen=True)
class Filtros:
    fecha_ini: date | None = None
    fecha_fin: date | None = None
    documento: int | None = None
    rangos: tuple = ()
    especialidades: tuple = ()
    ciudades: tuple = ()
    centros: tuple = ()

    def descripcion(self) -> str:
        partes = []
        if self.fecha_ini or self.fecha_fin:
            partes.append(f"Fechas: {self.fecha_ini or '...'} a {self.fecha_fin or '...'}")
        if self.documento:
            partes.append(f"Documento: {self.documento}")
        for nombre, v in (("Rango de edad", self.rangos), ("Especialidad", self.especialidades),
                          ("Ciudad", self.ciudades), ("Centro", self.centros)):
            if v:
                partes.append(f"{nombre}: {', '.join(v)}")
        return " | ".join(partes) or "Sin filtros (todos los datos)"


def _where(f: Filtros):
    c, p = ["1=1"], {}
    if f.fecha_ini:
        c.append("fecha_ingreso >= :fi"); p["fi"] = pd.Timestamp(f.fecha_ini).to_pydatetime()
    if f.fecha_fin:
        c.append("fecha_ingreso < :ff"); p["ff"] = (pd.Timestamp(f.fecha_fin) + pd.Timedelta(days=1)).to_pydatetime()
    if f.documento:
        c.append("documento = :doc"); p["doc"] = int(f.documento)
    for col, vals, pref in (("rango_edad", f.rangos, "r"), ("especialidad", f.especialidades, "e"),
                            ("ciudad", f.ciudades, "c"), ("centro", f.centros, "t")):
        if vals:
            ks = [f":{pref}{i}" for i in range(len(vals))]
            c.append(f"{col} IN ({','.join(ks)})")
            p.update({f"{pref}{i}": v for i, v in enumerate(vals)})
    return " AND ".join(c), p


_AGG = """COUNT(*) AS total,
  COALESCE(SUM(ha_venido_antes),0) AS reincidentes,
  COALESCE(SUM(remitido),0) AS remitidos,
  AVG(satisfaccion) AS satisfaccion_prom,
  COALESCE(SUM(CASE WHEN asistio = 0 THEN 1 ELSE 0 END),0) AS inasistencias,
  COALESCE(SUM(CASE WHEN asistio IS NOT NULL THEN 1 ELSE 0 END),0) AS con_asistencia"""


def _derivadas(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["total", "reincidentes", "remitidos", "satisfaccion_prom", "inasistencias", "con_asistencia"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    t = df["total"].where(df["total"] > 0)
    df["pct_reincidencia"] = (df["reincidentes"] / t * 100).round(2)
    df["pct_remision"] = (df["remitidos"] / t * 100).round(2)
    ca = df["con_asistencia"].where(df["con_asistencia"] > 0)
    df["pct_ausentismo"] = (df["inasistencias"] / ca * 100).round(2)
    return df


class CitaRepository:
    def hay_datos(self) -> bool:
        with engine.connect() as c:
            return c.execute(text("SELECT 1 FROM atenciones LIMIT 1")).first() is not None

    def opciones(self) -> dict:
        out = {}
        with engine.connect() as c:
            for k, col in (("especialidades", "especialidad"), ("ciudades", "ciudad"), ("centros", "centro")):
                out[k] = [r[0] for r in c.execute(text(f"SELECT DISTINCT {col} FROM atenciones ORDER BY 1")) if r[0]]
            r = c.execute(text("SELECT MIN(fecha_ingreso), MAX(fecha_ingreso) FROM atenciones")).first()
            out["fecha_min"], out["fecha_max"] = (pd.Timestamp(r[0]).date(), pd.Timestamp(r[1]).date()) if r[0] else (None, None)
        return out

    def kpis(self, f: Filtros) -> dict:
        w, p = _where(f)
        with engine.connect() as c:
            df = pd.read_sql(text(f"SELECT {_AGG}, COUNT(DISTINCT documento) AS pacientes FROM atenciones WHERE {w}"), c, params=p)
        df["pacientes"] = pd.to_numeric(df["pacientes"])
        df = _derivadas(df)
        return df.iloc[0].to_dict()

    def agrupar(self, campos: list[str], f: Filtros, orden: str = "total DESC", limite: int | None = None) -> pd.DataFrame:
        cols = [CAMPOS[c] for c in campos]
        w, p = _where(f)
        sql = f"SELECT {', '.join(cols)}, {_AGG} FROM atenciones WHERE {w} GROUP BY {', '.join(cols)} ORDER BY {orden}"
        if limite:
            sql += f" LIMIT {int(limite)}"
        with engine.connect() as c:
            df = pd.read_sql(text(sql), c, params=p)
        return _derivadas(df) if len(df) else df

    def detalle(self, f: Filtros, limite: int | None = 500, solo_reincidentes: bool = False) -> pd.DataFrame:
        w, p = _where(f)
        if solo_reincidentes:
            w += " AND ha_venido_antes = 1"
        sql = f"""SELECT tipo_documento, documento, edad, rango_edad, sexo, ciudad, centro, especialidad,
                  diagnostico, triage, estado_paciente, remitido, ha_venido_antes, satisfaccion,
                  fecha_ingreso, asistio, justificada
                  FROM atenciones WHERE {w} ORDER BY fecha_ingreso DESC"""
        if limite:
            sql += f" LIMIT {int(limite)}"
        with engine.connect() as c:
            return pd.read_sql(text(sql), c, params=p)

    def historial_paciente(self, documento: int) -> pd.DataFrame:
        with engine.connect() as c:
            return pd.read_sql(text("""SELECT fecha_ingreso, especialidad, centro, diagnostico, triage,
                    estado_paciente, ha_venido_antes, remitido, asistio, justificada
                    FROM atenciones WHERE documento = :d ORDER BY fecha_ingreso DESC"""), c, params={"d": int(documento)})

    def total_registros(self) -> int:
        with engine.connect() as c:
            return int(c.execute(text("SELECT COUNT(*) FROM atenciones")).scalar())
