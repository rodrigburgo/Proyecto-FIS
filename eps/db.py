"""Capa de persistencia: esquema y conexion (SQLite o PostgreSQL via SQLAlchemy)."""
from sqlalchemy import (BigInteger, Column, DateTime, Index, Integer, MetaData, String,
                        Table, Text, create_engine, event, func, select, text)

from .config import DATABASE_URL, PARAMETROS_DEFECTO

_es_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if _es_sqlite else {})

if _es_sqlite:
    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.close()

metadata = MetaData()
BigPK = BigInteger().with_variant(Integer, "sqlite")  # autoincrement en SQLite

usuarios = Table(
    "usuarios", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nombre", String(120), nullable=False),
    Column("correo", String(160), nullable=False, unique=True),
    Column("documento", String(30), nullable=False, unique=True),
    Column("clave_hash", String(300), nullable=False),
    Column("rol", String(20), nullable=False),
    Column("activo", Integer, nullable=False, server_default="1"),
    Column("creado", DateTime, server_default=func.now()),
)

auditoria = Table(
    "auditoria", metadata,
    Column("id", BigPK, primary_key=True, autoincrement=True),
    Column("fecha", DateTime, server_default=func.now(), index=True),
    Column("id_usuario", Integer, index=True),
    Column("accion", String(60), index=True),
    Column("detalle", Text),
)

cargas = Table(
    "cargas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nombre_archivo", String(255)),
    Column("hash_archivo", String(64), index=True),
    Column("fecha", DateTime, server_default=func.now()),
    Column("id_usuario", Integer),
    Column("estado", String(30)),  # PENDIENTE/VALIDANDO_FORMATO/PROCESANDO/COMPLETADO/ERROR_FORMATO/ELIMINADA
    Column("registros_ok", Integer, server_default="0"),
    Column("registros_error", Integer, server_default="0"),
    Column("mensaje", Text),
)

registros_error = Table(
    "registros_error", metadata,
    Column("id", BigPK, primary_key=True, autoincrement=True),
    Column("id_carga", Integer, index=True),
    Column("fila", Integer),
    Column("motivo", Text),
    Column("datos_json", Text),
)

atenciones = Table(
    "atenciones", metadata,
    Column("id", BigPK, primary_key=True, autoincrement=True),
    Column("id_carga", Integer, nullable=False),
    Column("tipo_documento", String(20)),
    Column("documento", BigInteger, nullable=False),
    Column("edad", Integer),
    Column("rango_edad", String(10)),
    Column("ciudad", String(80)),
    Column("centro", String(120)),
    Column("especialidad", String(80)),
    Column("remitido", Integer),
    Column("ha_venido_antes", Integer),
    Column("diagnostico", String(120)),
    Column("sexo", String(20)),
    Column("triage", String(10)),
    Column("estado_paciente", String(60)),
    Column("medicamento", String(120)),
    Column("satisfaccion", Integer),
    Column("fecha_ingreso", DateTime, nullable=False),
    Column("mes", String(7)),
    Column("asistio", Integer),      # 1 asistio / 0 falto / NULL sin dato
    Column("justificada", Integer),  # 1 justificada / 0 injustificada
    Index("ix_at_fecha", "fecha_ingreso"),
    Index("ix_at_doc_fecha", "documento", "fecha_ingreso"),
    Index("ix_at_esp", "especialidad"),
    Index("ix_at_rango", "rango_edad"),
    Index("ix_at_carga", "id_carga"),
    Index("ix_at_centro", "centro"),
    Index("ix_at_ciudad", "ciudad"),
)

alertas = Table(
    "alertas_reincidencia", metadata,
    Column("id", BigPK, primary_key=True, autoincrement=True),
    Column("tipo_documento", String(20)),
    Column("documento", BigInteger, index=True),
    Column("criterio", String(20), index=True),  # INASISTENCIA (RN-02) | FRECUENCIA
    Column("n_eventos", Integer),
    Column("fecha_inicio", DateTime),
    Column("fecha_fin", DateTime),
    Column("nivel_riesgo", String(10)),
    Column("fecha_generacion", DateTime, server_default=func.now()),
)

parametros = Table(
    "parametros", metadata,
    Column("clave", String(60), primary_key=True),
    Column("valor", String(200)),
)


def init_db():
    metadata.create_all(engine)
    with engine.begin() as conn:
        for k, v in PARAMETROS_DEFECTO.items():
            existe = conn.execute(select(parametros.c.clave).where(parametros.c.clave == k)).first()
            if not existe:
                conn.execute(parametros.insert().values(clave=k, valor=v))


def ping() -> bool:
    with engine.connect() as c:
        return c.execute(text("SELECT 1")).scalar() == 1
