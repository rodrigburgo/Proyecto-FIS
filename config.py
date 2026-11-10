import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# SQLite por defecto (cero configuracion). Para produccion usa PostgreSQL:
#   set EPS_DATABASE_URL=postgresql+psycopg2://usuario:clave@host:5432/eps_tracker
DATABASE_URL = os.getenv("EPS_DATABASE_URL", f"sqlite:///{DATA_DIR / 'eps_tracker.db'}")

CHUNK_SIZE = 50_000          # filas procesadas por bloque al cargar archivos
MAX_ERRORES_GUARDADOS = 10_000  # tope de filas con error almacenadas por carga

ROL_ANALISTA = "ANALISTA"
ROL_ADMIN = "ADMINISTRADOR"
ROLES = [ROL_ANALISTA, ROL_ADMIN]

# RN-03: acceso por roles
PERMISOS = {
    "Dashboard": [ROL_ANALISTA, ROL_ADMIN],
    "Alertas de reincidencia": [ROL_ANALISTA, ROL_ADMIN],
    "Cargar archivo": [ROL_ANALISTA],
    "Historial de cargas": [ROL_ANALISTA],
    "Parámetros de métricas": [ROL_ANALISTA],
    "Reportes": [ROL_ADMIN],
    "Auditoría": [ROL_ADMIN],
    "Usuarios y permisos": [ROL_ADMIN],
    "Cambiar contraseña": [ROL_ANALISTA, ROL_ADMIN],
}

# Usuarios iniciales (solo se crean si la tabla esta vacia). CAMBIAR en el primer ingreso.
ADMIN_INICIAL = ("Administrador", "admin@eps.com", "10000001", "Admin123!", ROL_ADMIN)
ANALISTA_INICIAL = ("Analista de Datos", "analista@eps.com", "10000002", "Analista123!", ROL_ANALISTA)

PARAMETROS_DEFECTO = {"umbral_reincidencia": "3", "ventana_meses": "6"}
