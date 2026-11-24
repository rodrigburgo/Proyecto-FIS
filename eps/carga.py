"""RF-02, RF-03, RF-04 / CU-01, CU-06, CU-08, CU-09: CargaService (ETL por bloques)."""
import csv
import hashlib
import io
import json
from typing import Callable, Iterator

import pandas as pd
from sqlalchemy import insert, select, text, update

from . import auditoria, reincidencia, validador
from .config import CHUNK_SIZE, MAX_ERRORES_GUARDADOS
from .db import atenciones, cargas, engine, registros_error


class ArchivoDuplicado(Exception):
    pass


def _leer_csv(data: bytes) -> Iterator[pd.DataFrame]:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            muestra = data[:20000].decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(muestra.split("\n", 1)[0], delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    yield from pd.read_csv(io.BytesIO(data), sep=sep, encoding=enc, dtype=str,
                           chunksize=CHUNK_SIZE, keep_default_na=False, na_values=[""])


def _leer_excel(data: bytes) -> Iterator[pd.DataFrame]:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    filas = wb.worksheets[0].iter_rows(values_only=True)
    cab = [("" if c is None else str(c)) for c in next(filas)]
    buf = []
    for f in filas:
        if f is None or all(v is None for v in f):
            continue
        buf.append(f[:len(cab)])
        if len(buf) >= CHUNK_SIZE:
            yield pd.DataFrame(buf, columns=cab)
            buf = []
    if buf:
        yield pd.DataFrame(buf, columns=cab)
    wb.close()


def leer_bloques(data: bytes, nombre: str) -> Iterator[pd.DataFrame]:
    n = nombre.lower()
    if n.endswith(".csv") or n.endswith(".txt"):
        return _leer_csv(data)
    if n.endswith((".xlsx", ".xlsm")):
        return _leer_excel(data)
    raise ValueError("Formato no soportado. Usa CSV o Excel (.xlsx).")


def _set_estado(id_carga, estado, **extra):
    with engine.begin() as c:
        c.execute(update(cargas).where(cargas.c.id == id_carga).values(estado=estado, **extra))


def _errores_a_filas(id_carga, err: pd.DataFrame, offset: int):
    out = []
    datos = err.drop(columns=["motivo"]).astype(object).where(err.drop(columns=["motivo"]).notna(), None)
    for (idx, motivo), (_, fila) in zip(err["motivo"].items(), datos.iterrows()):
        out.append({"id_carga": id_carga, "fila": int(offset + idx + 2), "motivo": motivo,
                    "datos_json": json.dumps({k: (None if v is None else str(v)) for k, v in fila.items()},
                                             ensure_ascii=False)})
    return out


class CargaService:
    def procesar(self, data: bytes, nombre: str, id_usuario: int,
                 progreso: Callable[[int], None] | None = None) -> dict:
        """Estados: PENDIENTE -> VALIDANDO_FORMATO -> PROCESANDO -> COMPLETADO | ERROR_FORMATO."""
        h = hashlib.sha256(data).hexdigest()
        with engine.connect() as c:
            dup = c.execute(select(cargas.c.id, cargas.c.fecha).where(
                (cargas.c.hash_archivo == h) & (cargas.c.estado == "COMPLETADO"))).first()
        if dup:
            raise ArchivoDuplicado(f"Este archivo ya fue cargado (carga #{dup.id}, {dup.fecha:%Y-%m-%d %H:%M}). "
                                   "Elimina esa carga si quieres volver a cargarlo.")

        with engine.begin() as c:
            id_carga = c.execute(insert(cargas).values(
                nombre_archivo=nombre, hash_archivo=h, id_usuario=id_usuario, estado="PENDIENTE")).inserted_primary_key[0]
        _set_estado(id_carga, "VALIDANDO_FORMATO")

        ok_total = err_total = filas_vistas = 0
        errores_guardados = 0
        try:
            bloques = leer_bloques(data, nombre)
            with engine.begin() as conn:  # una sola transaccion: todo o nada (RNF-04)
                for i, bloque in enumerate(bloques):
                    bloque = validador.normalizar_columnas(bloque)
                    if i == 0:
                        ok, faltan = validador.validar_columnas(bloque)
                        if not ok:
                            raise ValueError("Faltan columnas obligatorias: " + ", ".join(faltan))
                    df_ok, df_err = validador.validar_filas(bloque)
                    if len(df_ok):
                        df_ok.insert(0, "id_carga", id_carga)
                        df_ok.to_sql("atenciones", conn, if_exists="append", index=False, chunksize=10_000)
                    if len(df_err) and errores_guardados < MAX_ERRORES_GUARDADOS:
                        filas = _errores_a_filas(id_carga, df_err, filas_vistas)[:MAX_ERRORES_GUARDADOS - errores_guardados]
                        conn.execute(insert(registros_error), filas)
                        errores_guardados += len(filas)
                    ok_total += len(df_ok)
                    err_total += len(df_err)
                    filas_vistas += len(bloque)
                    if progreso:
                        progreso(filas_vistas)
                if filas_vistas == 0:
                    raise ValueError("El archivo está vacío.")
                if ok_total == 0:
                    raise ValueError("Ninguna fila superó la validación de formato.")
        except Exception as e:
            _set_estado(id_carga, "ERROR_FORMATO", mensaje=str(e)[:900], registros_ok=0, registros_error=err_total)
            auditoria.registrar(id_usuario, "CARGA_FALLIDA", f"{nombre}: {e}")
            raise

        _set_estado(id_carga, "PROCESANDO", registros_ok=ok_total, registros_error=err_total)
        alertas = reincidencia.recalcular_alertas()
        _set_estado(id_carga, "COMPLETADO")
        auditoria.registrar(id_usuario, "CARGA_EXITOSA",
                            f"{nombre}: {ok_total} ok, {err_total} con error (carga #{id_carga})")
        return {"id_carga": id_carga, "ok": ok_total, "errores": err_total, "alertas": alertas}

    # ---- CU-08 historial
    def historial(self) -> pd.DataFrame:
        with engine.connect() as c:
            return pd.read_sql(text("""SELECT c.id, c.fecha, c.nombre_archivo AS archivo, c.estado,
                    c.registros_ok, c.registros_error, COALESCE(u.correo,'') AS usuario, c.mensaje
                    FROM cargas c LEFT JOIN usuarios u ON u.id = c.id_usuario ORDER BY c.id DESC"""), c)

    # ---- CU-09 corregir / eliminar errores
    def errores(self, id_carga: int) -> pd.DataFrame:
        with engine.connect() as c:
            filas = c.execute(select(registros_error).where(registros_error.c.id_carga == id_carga)
                              .order_by(registros_error.c.id).limit(5000)).all()
        regs = []
        for f in filas:
            d = json.loads(f.datos_json)
            regs.append({"_id_error": f.id, "fila": f.fila, "motivo": f.motivo, **d})
        return pd.DataFrame(regs)

    def reintentar(self, id_carga: int, corregido: pd.DataFrame, id_usuario: int) -> dict:
        trabajo = corregido.drop(columns=["fila", "motivo"], errors="ignore")
        ids = trabajo.pop("_id_error")
        base = validador.normalizar_columnas(trabajo)
        df_ok, df_err = validador.validar_filas(base)
        with engine.begin() as conn:
            if len(df_ok):
                df_ok.insert(0, "id_carga", id_carga)
                df_ok.to_sql("atenciones", conn, if_exists="append", index=False)
                conn.execute(registros_error.delete().where(registros_error.c.id.in_([int(ids[i]) for i in df_ok.index])))
            for i in df_err.index:  # los que siguen mal: actualizar motivo y datos
                conn.execute(update(registros_error).where(registros_error.c.id == int(ids[i])).values(
                    motivo=df_err.loc[i, "motivo"],
                    datos_json=json.dumps({k: (None if pd.isna(v) else str(v)) for k, v in trabajo.loc[i].items()}, ensure_ascii=False)))
            quedan = conn.execute(text("SELECT COUNT(*) FROM registros_error WHERE id_carga=:i"), {"i": id_carga}).scalar()
            conn.execute(update(cargas).where(cargas.c.id == id_carga).values(
                registros_ok=cargas.c.registros_ok + len(df_ok), registros_error=quedan))
        reincidencia.recalcular_alertas()
        auditoria.registrar(id_usuario, "ERRORES_CORREGIDOS", f"carga #{id_carga}: {len(df_ok)} recuperados")
        return {"recuperados": len(df_ok), "persisten": len(df_err)}

    def eliminar_errores(self, ids: list[int], id_carga: int, id_usuario: int):
        with engine.begin() as conn:
            conn.execute(registros_error.delete().where(registros_error.c.id.in_(ids)))
            quedan = conn.execute(text("SELECT COUNT(*) FROM registros_error WHERE id_carga=:i"), {"i": id_carga}).scalar()
            conn.execute(update(cargas).where(cargas.c.id == id_carga).values(registros_error=quedan))
        auditoria.registrar(id_usuario, "ERRORES_ELIMINADOS", f"carga #{id_carga}: {len(ids)} registros")

    def eliminar_carga(self, id_carga: int, id_usuario: int):
        with engine.begin() as conn:
            conn.execute(atenciones.delete().where(atenciones.c.id_carga == id_carga))
            conn.execute(registros_error.delete().where(registros_error.c.id_carga == id_carga))
            conn.execute(update(cargas).where(cargas.c.id == id_carga).values(estado="ELIMINADA"))
        reincidencia.recalcular_alertas()
        auditoria.registrar(id_usuario, "CARGA_ELIMINADA", f"carga #{id_carga}")
