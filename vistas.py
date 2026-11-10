"""Capa Vista (Streamlit). Cada funcion es una pagina; llama a servicios/repositorios (nunca a SQL directo)."""
import pandas as pd
import streamlit as st

from . import auditoria, graficas, parametros, reincidencia
from .carga import ArchivoDuplicado, CargaService
from .config import ROLES
from .exportacion import a_excel, a_pdf
from .repositorio import CitaRepository, Filtros
from .seguridad import AuthService, UsuarioRepository, UsuarioYaExiste
from .validador import NOMBRES_LEGIBLES, OBLIGATORIAS

REPO, CARGAS, AUTH, USERS = CitaRepository(), CargaService(), AuthService(), UsuarioRepository()


def fmt(n, dec=0):
    if n is None or pd.isna(n):
        return "—"
    return f"{n:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------- consultas con cache (se invalida al cargar/eliminar datos) ----------
@st.cache_data(ttl=600, show_spinner=False)
def _opciones(): return REPO.opciones()
@st.cache_data(ttl=600, show_spinner=False)
def _kpis(f): return REPO.kpis(f)
@st.cache_data(ttl=600, show_spinner=False)
def _agrupar(campos, f, orden="total DESC"): return REPO.agrupar(list(campos), f, orden)
@st.cache_data(ttl=600, show_spinner=False)
def _alertas(criterio): return reincidencia.listar_alertas(criterio)


def invalidar_cache():
    st.cache_data.clear()


def _sin_datos() -> bool:
    if not REPO.hay_datos():
        st.info("Aún no hay datos cargados. Un Analista de Datos debe cargar un archivo en **Cargar archivo**.")
        return True
    return False


# ---------- filtros (CU-10) ----------
def filtros_sidebar() -> Filtros:
    o = _opciones()
    st.sidebar.markdown("### Filtros")
    rango = st.sidebar.date_input("Fecha de ingreso", value=(o["fecha_min"], o["fecha_max"]),
                                  min_value=o["fecha_min"], max_value=o["fecha_max"])
    fi, ff = (rango[0], rango[1]) if isinstance(rango, (tuple, list)) and len(rango) == 2 else (o["fecha_min"], o["fecha_max"])
    from .validador import ETIQUETAS_EDAD
    rangos = st.sidebar.multiselect("Rango de edad", ETIQUETAS_EDAD)
    esp = st.sidebar.multiselect("Especialidad", o["especialidades"])
    ciu = st.sidebar.multiselect("Ciudad", o["ciudades"])
    cen = st.sidebar.multiselect("Centro de atención", o["centros"])
    doc = st.sidebar.text_input("Documento del paciente")
    doc = int(doc) if doc.strip().isdigit() else None
    if doc is None and doc is not None:
        pass
    return Filtros(fi, ff, doc, tuple(rangos), tuple(esp), tuple(ciu), tuple(cen))


# ---------- CU-02 Dashboard ----------
def pagina_dashboard(usuario):
    st.title("Dashboard de atención y reincidencia")
    if _sin_datos():
        return
    f = filtros_sidebar()
    k = _kpis(f)
    if not k["total"]:
        st.warning("No hay registros para los filtros seleccionados.")
        return
    st.caption(f.descripcion())
    c = st.columns(6)
    c[0].metric("Atenciones", fmt(k["total"]))
    c[1].metric("Pacientes únicos", fmt(k["pacientes"]))
    c[2].metric("Reincidentes (ha venido antes)", f"{fmt(k['pct_reincidencia'], 1)} %")
    c[3].metric("Remitidos a otra especialidad", f"{fmt(k['pct_remision'], 1)} %")
    c[4].metric("Satisfacción promedio", f"{fmt(k['satisfaccion_prom'], 2)} / 5")
    c[5].metric("Ausentismo", f"{fmt(k['pct_ausentismo'], 1)} %" if k["con_asistencia"] else "Sin datos")

    esp, edad = _agrupar(("especialidad",), f), _agrupar(("rango_edad",), f)
    a, b = st.columns(2)
    a.plotly_chart(graficas.serie_mensual(_agrupar(("mes",), f, "mes")), width="stretch")
    b.plotly_chart(graficas.barras_h(esp, "especialidad", "total", "Atenciones por especialidad"), width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(graficas.rango_edad(edad), width="stretch")
    b.plotly_chart(graficas.barras_h(esp, "especialidad", "pct_remision", "% de remisión por especialidad", ".1f", "#2C7BB6"), width="stretch")
    a, b = st.columns(2)
    cruce = _agrupar(("especialidad", "rango_edad"), f)
    a.plotly_chart(graficas.heatmap(cruce, "pct_reincidencia", "% de reincidencia: especialidad × rango de edad"), width="stretch")
    b.plotly_chart(graficas.dona(_agrupar(("triage",), f), "triage", "Nivel de triage", graficas.ORDEN_TRIAGE), width="stretch")
    a, b, c3 = st.columns(3)
    a.plotly_chart(graficas.barras_h(_agrupar(("diagnostico",), f), "diagnostico", "total", "Top 10 diagnósticos", top=10), width="stretch")
    b.plotly_chart(graficas.columnas(_agrupar(("satisfaccion",), f, "satisfaccion"), "satisfaccion", "total", "Satisfacción (1-5)"), width="stretch")
    c3.plotly_chart(graficas.barras_h(_agrupar(("ciudad",), f), "ciudad", "total", "Atenciones por ciudad"), width="stretch")

    if k["con_asistencia"]:
        st.subheader("Ausentismo")
        a, b, c3 = st.columns(3)
        a.plotly_chart(graficas.barras_h(esp.dropna(subset=["pct_ausentismo"]), "especialidad", "pct_ausentismo", "% ausentismo por especialidad", ".1f"), width="stretch")
        b.plotly_chart(graficas.columnas(edad.dropna(subset=["pct_ausentismo"]), "rango_edad", "pct_ausentismo", "% ausentismo por rango de edad"), width="stretch")
        c3.plotly_chart(graficas.linea(_agrupar(("mes",), f, "mes").dropna(subset=["pct_ausentismo"]), "mes", "pct_ausentismo", "% ausentismo por mes"), width="stretch")

    with st.expander("Ver registros (primeros 500)"):
        st.dataframe(REPO.detalle(f, 500), width="stretch", hide_index=True)


# ---------- CU-03 / CU-11 Alertas ----------
def _detalle_paciente(key):
    doc = st.text_input("Ver historial de un paciente (documento)", key=key)
    if doc.strip().isdigit():
        h = REPO.historial_paciente(int(doc))
        st.dataframe(h, width="stretch", hide_index=True) if len(h) else st.info("Sin registros para ese documento.")


def pagina_alertas(usuario):
    st.title("Alertas de reincidencia")
    if _sin_datos():
        return
    umbral, ventana = parametros.umbral_y_ventana()
    st.caption(f"Regla vigente: ≥ {umbral} eventos en {ventana} meses (configurable en *Parámetros de métricas*).")
    t1, t2, t3 = st.tabs(["Inasistencias (RN-02)", "Atenciones frecuentes", "Reincidentes declarados"])
    with t1:
        df = _alertas("INASISTENCIA")
        if REPO.kpis(Filtros())["con_asistencia"] == 0:
            st.info("La base cargada no trae la columna **Estado de la cita** (Asistió/Faltó), por eso no se pueden "
                    "calcular inasistencias. Carga un archivo con esa columna para activar la RN-02.")
        elif df.empty:
            st.success("Ningún paciente cumple el criterio de reincidencia por inasistencia.")
        else:
            st.metric("Pacientes con Alerta de Reincidencia", fmt(len(df)))
            st.dataframe(df, width="stretch", hide_index=True)
            _detalle_paciente("det1")
    with t2:
        df = _alertas("FRECUENCIA")
        if df.empty:
            st.success(f"Ningún paciente tiene {umbral} o más atenciones en {ventana} meses.")
        else:
            st.metric("Pacientes con atenciones frecuentes", fmt(len(df)))
            st.dataframe(df, width="stretch", hide_index=True)
            _detalle_paciente("det2")
    with t3:
        st.caption("Pacientes con la marca **Ha venido antes = Sí** de la base de datos (usa los filtros de la izquierda).")
        f = filtros_sidebar()
        k = _kpis(f)
        c = st.columns(3)
        c[0].metric("Atenciones de reincidentes", fmt(k["reincidentes"]))
        c[1].metric("% sobre el total", f"{fmt(k['pct_reincidencia'], 1)} %")
        c[2].metric("Total filtrado", fmt(k["total"]))
        if k["total"]:
            a, b = st.columns(2)
            a.plotly_chart(graficas.rango_edad(_agrupar(("rango_edad",), f)), width="stretch")
            b.plotly_chart(graficas.barras_h(_agrupar(("especialidad",), f), "especialidad", "pct_reincidencia", "% reincidencia por especialidad", ".1f"), width="stretch")
            st.dataframe(REPO.detalle(f, 1000, solo_reincidentes=True), width="stretch", hide_index=True)
            if st.button("Preparar descarga CSV de reincidentes"):
                csv = REPO.detalle(f, None, solo_reincidentes=True).to_csv(index=False).encode("utf-8-sig")
                st.download_button("Descargar CSV", csv, "reincidentes.csv", "text/csv")


# ---------- CU-01 Cargar ----------
def pagina_carga(usuario):
    st.title("Cargar archivo de citas")
    with st.expander("Columnas del archivo", expanded=False):
        st.markdown("**Obligatorias (RN-01):** " + ", ".join(NOMBRES_LEGIBLES[c] for c in OBLIGATORIAS))
        st.markdown("**Opcionales:** " + ", ".join(v for k, v in NOMBRES_LEGIBLES.items() if k not in OBLIGATORIAS) +
                    ". Si incluyes *Estado de la cita* (Asistió/Faltó) se activan las métricas de ausentismo y la RN-02.")
        plantilla = ",".join(NOMBRES_LEGIBLES.values()) + "\n"
        st.download_button("Descargar plantilla CSV", plantilla.encode("utf-8-sig"), "plantilla_eps_tracker.csv", "text/csv")
    archivo = st.file_uploader("Selecciona un archivo CSV o Excel (.xlsx)", type=["csv", "xlsx"])
    if archivo and st.button("Cargar", type="primary"):
        barra = st.progress(0.0, text="Validando formato…")
        try:
            r = CARGAS.procesar(archivo.getvalue(), archivo.name, usuario.id,
                                progreso=lambda n: barra.progress(0.5, text=f"Procesando… {fmt(n)} filas"))
            barra.progress(1.0, text="Listo")
            invalidar_cache()
            st.success(f"Registros guardados: {fmt(r['ok'])}. Con error: {fmt(r['errores'])}.")
            if r["errores"]:
                st.warning("Hay registros con error: corrígelos o elimínalos en **Historial de cargas**.")
            if r["alertas"]["INASISTENCIA"] or r["alertas"]["FRECUENCIA"]:
                st.info(f"Alertas generadas — inasistencia: {r['alertas']['INASISTENCIA']}, frecuencia: {r['alertas']['FRECUENCIA']}")
        except ArchivoDuplicado as e:
            barra.empty(); st.warning(str(e))
        except Exception as e:
            barra.empty(); st.error(f"Corregir formato: {e}")


# ---------- CU-08 / CU-09 Historial ----------
def pagina_historial(usuario):
    st.title("Historial de cargas")
    h = CARGAS.historial()
    if h.empty:
        st.info("Todavía no se han realizado cargas.")
        return
    st.dataframe(h, width="stretch", hide_index=True)
    st.subheader("Corregir o eliminar registros con error")
    con_err = h[h["registros_error"] > 0]["id"].tolist()
    if not con_err:
        st.success("No hay registros con error pendientes.")
    else:
        id_c = st.selectbox("Carga", con_err, format_func=lambda i: f"#{i} — {h.loc[h.id == i, 'archivo'].iloc[0]}")
        err = CARGAS.errores(id_c)
        if len(err) < int(h.loc[h.id == id_c, "registros_error"].iloc[0]):
            st.caption("Se muestran hasta 5.000 registros con error por carga.")
        err.insert(0, "eliminar", False)
        ed = st.data_editor(err, hide_index=True, width="stretch", disabled=["fila", "motivo"],
                            column_config={"_id_error": None}, key=f"ed{id_c}")
        a, b = st.columns(2)
        if a.button("Reintentar con mis correcciones", type="primary"):
            r = CARGAS.reintentar(id_c, ed.drop(columns=["eliminar"]).reset_index(drop=True), usuario.id)
            invalidar_cache()
            st.success(f"Recuperados: {r['recuperados']}. Siguen con error: {r['persisten']}.")
            st.rerun()
        if b.button("Eliminar los marcados"):
            ids = ed.loc[ed["eliminar"], "_id_error"].astype(int).tolist()
            if ids:
                CARGAS.eliminar_errores(ids, id_c, usuario.id); st.rerun()
            else:
                st.warning("Marca al menos un registro en la columna 'eliminar'.")
    st.subheader("Eliminar una carga completa")
    activas = h[h["estado"] == "COMPLETADO"]["id"].tolist()
    if activas:
        id_e = st.selectbox("Carga a eliminar", activas, key="del")
        if st.checkbox("Entiendo que se borrarán todos sus registros") and st.button("Eliminar carga"):
            CARGAS.eliminar_carga(id_e, usuario.id)
            invalidar_cache(); st.success("Carga eliminada."); st.rerun()


# ---------- CU-07 Parámetros ----------
def pagina_parametros(usuario):
    st.title("Parámetros de métricas")
    u, v = parametros.umbral_y_ventana()
    c1, c2 = st.columns(2)
    nu = c1.number_input("Umbral de eventos (RN-02: 3)", 1, 50, u)
    nv = c2.number_input("Ventana en meses (RN-02: 6)", 1, 60, v)
    if st.button("Guardar y recalcular alertas", type="primary"):
        parametros.guardar(int(nu), int(nv))
        res = reincidencia.recalcular_alertas()
        auditoria.registrar(usuario.id, "PARAMETROS_ACTUALIZADOS", f"umbral={nu}, ventana={nv}")
        invalidar_cache()
        st.success(f"Guardado. Alertas — inasistencia: {res['INASISTENCIA']}, frecuencia: {res['FRECUENCIA']}")


# ---------- CU-12 / CU-13 Reportes ----------
def pagina_reportes(usuario):
    st.title("Reportes de ausentismo y atención")
    if _sin_datos():
        return
    f = filtros_sidebar()
    k = _kpis(f)
    if not k["total"]:
        st.warning("No hay registros para los filtros seleccionados.")
        return
    esp, edad = _agrupar(("especialidad",), f), _agrupar(("rango_edad",), f)
    mes, centro = _agrupar(("mes",), f, "mes"), _agrupar(("centro",), f)
    cols = {"total": "Atenciones", "reincidentes": "Reincidentes", "remitidos": "Remitidos", "satisfaccion_prom": "Satisfacción prom.",
            "inasistencias": "Inasistencias", "con_asistencia": "Citas con dato de asistencia", "pct_reincidencia": "% reincidencia",
            "pct_remision": "% remisión", "pct_ausentismo": "% ausentismo"}
    ren = lambda d, n: d.rename(columns={**cols, n: n.replace("_", " ").capitalize()}).round(2)
    tablas = {"Por especialidad": ren(esp, "especialidad"), "Por rango de edad": ren(edad, "rango_edad"),
              "Por mes": ren(mes, "mes"), "Por centro": ren(centro, "centro")}
    kp = {"Atenciones": fmt(k["total"]), "Pacientes únicos": fmt(k["pacientes"]), "% reincidencia": fmt(k["pct_reincidencia"], 1),
          "% remisión": fmt(k["pct_remision"], 1), "Satisfacción": fmt(k["satisfaccion_prom"], 2),
          "% ausentismo": fmt(k["pct_ausentismo"], 1)}
    st.caption(f.descripcion())
    st.dataframe(pd.DataFrame([kp]), hide_index=True, width="stretch")
    for n, d in tablas.items():
        with st.expander(n):
            st.dataframe(d, hide_index=True, width="stretch")
    hojas = {"Resumen": pd.DataFrame({"Indicador": list(kp), "Valor": list(kp.values())}), **tablas,
             "Alertas inasistencia": _alertas("INASISTENCIA"), "Atenciones frecuentes": _alertas("FRECUENCIA")}
    log = lambda fmt_: auditoria.registrar(usuario.id, "REPORTE_EXPORTADO", f"{fmt_} | {f.descripcion()}")
    a, b, c = st.columns(3)
    a.download_button("⬇ Excel", a_excel(hojas), "reporte_eps_tracker.xlsx", on_click=log, args=("xlsx",),
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    b.download_button("⬇ PDF", a_pdf("Reporte EPS Tracker", f.descripcion(), kp, tablas), "reporte_eps_tracker.pdf",
                      "application/pdf", on_click=log, args=("pdf",))
    if c.button("Preparar CSV con el detalle filtrado"):
        st.session_state["csv_detalle"] = REPO.detalle(f, None).to_csv(index=False).encode("utf-8-sig")
    if "csv_detalle" in st.session_state:
        c.download_button("⬇ Descargar CSV (listo para Power BI)", st.session_state["csv_detalle"],
                          "detalle_eps_tracker.csv", "text/csv", on_click=log, args=("csv",))


# ---------- CU-14 Auditoría ----------
def pagina_auditoria(usuario):
    st.title("Historial de auditoría")
    c1, c2 = st.columns([2, 1])
    acc = c1.selectbox("Acción", ["(todas)"] + auditoria.acciones_distintas())
    lim = c2.number_input("Máximo de filas", 50, 5000, 500, step=50)
    st.dataframe(auditoria.listar(int(lim), None if acc == "(todas)" else acc), width="stretch", hide_index=True)


# ---------- CU-04 Usuarios ----------
def pagina_usuarios(usuario):
    st.title("Usuarios y permisos")
    us = USERS.listar()
    st.dataframe(pd.DataFrame([u.__dict__ for u in us]), hide_index=True, width="stretch")
    st.subheader("Crear usuario")
    with st.form("nuevo_usuario", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nombre, correo = c1.text_input("Nombre"), c2.text_input("Correo")
        doc, rol = c1.text_input("Documento"), c2.selectbox("Rol", ROLES)
        clave = st.text_input("Contraseña temporal (mín. 8)", type="password")
        if st.form_submit_button("Crear", type="primary"):
            if not (nombre and correo and doc and len(clave) >= 8):
                st.error("Completa todos los campos (contraseña de mínimo 8 caracteres).")
            else:
                try:
                    USERS.crear(nombre, correo, doc, clave, rol)
                    auditoria.registrar(usuario.id, "USUARIO_CREADO", f"{correo} ({rol})")
                    st.success("Usuario creado."); st.rerun()
                except UsuarioYaExiste:
                    st.error("El usuario ya existe.")
    st.subheader("Modificar permisos / inactivar")
    sel = st.selectbox("Usuario", us, format_func=lambda u: f"{u.correo} — {u.rol} — {'activo' if u.activo else 'inactivo'}")
    nuevo_rol = st.selectbox("Rol", ROLES, index=ROLES.index(sel.rol), key=f"rol{sel.id}")
    a, b = st.columns(2)
    if a.button("Guardar rol"):
        USERS.actualizar_rol(sel.id, nuevo_rol)
        auditoria.registrar(usuario.id, "ROL_ACTUALIZADO", f"{sel.correo} -> {nuevo_rol}"); st.rerun()
    if b.button("Inactivar cuenta" if sel.activo else "Reactivar cuenta"):
        if sel.id == usuario.id:
            st.error("No puedes inactivar tu propia cuenta.")
        else:
            USERS.set_activo(sel.id, not sel.activo)
            auditoria.registrar(usuario.id, "USUARIO_INACTIVADO" if sel.activo else "USUARIO_REACTIVADO", sel.correo); st.rerun()


# ---------- CU-15 Cambiar contraseña ----------
def pagina_clave(usuario):
    st.title("Cambiar contraseña")
    with st.form("clave"):
        actual = st.text_input("Contraseña actual", type="password")
        nueva = st.text_input("Nueva contraseña (mín. 8)", type="password")
        if st.form_submit_button("Actualizar", type="primary"):
            ok, msg = AUTH.cambiar_clave(usuario, actual, nueva)
            (st.success if ok else st.error)(msg)
