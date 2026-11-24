"""EPS Tracker - punto de entrada.  Ejecutar:  streamlit run app.py"""
import streamlit as st

from eps import auditoria, db, seguridad, vistas
from eps.config import PERMISOS

st.set_page_config(page_title="EPS Tracker", page_icon="🩺", layout="wide")


@st.cache_resource
def _iniciar():
    db.init_db()
    seguridad.sembrar_usuarios_iniciales()
    return True


_iniciar()

PAGINAS = {
    "Dashboard": vistas.pagina_dashboard,
    "Alertas de reincidencia": vistas.pagina_alertas,
    "Cargar archivo": vistas.pagina_carga,
    "Historial de cargas": vistas.pagina_historial,
    "Parámetros de métricas": vistas.pagina_parametros,
    "Reportes": vistas.pagina_reportes,
    "Auditoría": vistas.pagina_auditoria,
    "Usuarios y permisos": vistas.pagina_usuarios,
    "Cambiar contraseña": vistas.pagina_clave,
}


def login():
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.title("🩺 EPS Tracker")
        st.caption("Sistema de análisis y seguimiento de ausentismo")
        with st.form("login"):
            correo = st.text_input("Correo")
            clave = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Iniciar sesión", type="primary", width="stretch"):
                u, msg = vistas.AUTH.autenticar(correo, clave)
                if u:
                    st.session_state["usuario"] = u
                    st.rerun()
                else:
                    st.error(msg)


def main():
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return login()
    permitidas = [p for p in PAGINAS if seguridad.puede_acceder(usuario.rol, p)]
    with st.sidebar:
        st.markdown(f"### 🩺 EPS Tracker\n**{usuario.nombre}**  \n`{usuario.rol}`")
        pagina = st.radio("Menú", permitidas, label_visibility="collapsed")
        if st.button("Cerrar sesión", width="stretch"):
            auditoria.registrar(usuario.id, "LOGOUT", "")
            st.session_state.clear()
            st.rerun()
        st.divider()
    PAGINAS[pagina](usuario)


main()
