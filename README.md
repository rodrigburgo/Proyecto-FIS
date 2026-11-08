# EPS Tracker

Carga archivos de atenciones/citas (CSV o Excel), los valida, los guarda en una base de datos y muestra un
dashboard con filtros, alertas de reincidencia, reportes (Excel/PDF/CSV), auditoría y gestión de usuarios.

## Ejecutar
```bash
pip install -r requirements.txt
streamlit run app.py
```
Abre http://localhost:8501. Usuarios iniciales (**cámbialos** en *Cambiar contraseña*):

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | admin@eps.com | Admin123! |
| Analista de Datos | analista@eps.com | Analista123! |

Flujo: entra como **analista** → *Cargar archivo* → sube tu Excel/CSV → entra como **admin** o analista → *Dashboard*.

## Datos de prueba con ausentismo
Tu base de 100k no trae la columna *Estado de la cita* (Asistió/Faltó), por eso no puede calcular inasistencias.
Para probar la RN-02 completa:
```bash
python generar_datos_prueba.py --filas 300000 --salida datos_prueba.csv
```

## Estructura (MVC + Repository, igual que el informe)
| Capa | Archivos |
|---|---|
| Vista | `app.py`, `eps/vistas.py`, `eps/graficas.py` |
| Controlador/Servicios | `eps/carga.py` (CargaService), `eps/seguridad.py` (AuthService), `eps/reincidencia.py` (MotorReincidencia), `eps/validador.py` (ValidadorArchivo), `eps/exportacion.py`, `eps/auditoria.py`, `eps/parametros.py` |
| Repositorios | `eps/repositorio.py` (CitaRepository), `UsuarioRepository` en `eps/seguridad.py` |
| Persistencia | `eps/db.py`, `eps/config.py` |

## PostgreSQL (producción / muchos millones de filas)
```bash
pip install psycopg2-binary
set EPS_DATABASE_URL=postgresql+psycopg2://usuario:clave@host:5432/eps_tracker   # Linux/Mac: export
```
Las tablas se crean solas. Todas las gráficas se calculan con `GROUP BY` en la base de datos, no en memoria.

## Power BI
- Reportes → *CSV con el detalle filtrado* o el Excel exportado se abren directo en Power BI.
- O conecta Power BI a la base (PostgreSQL) y usa la tabla `atenciones`.
- Cada gráfica del dashboard se puede descargar como PNG desde su barra (ícono de cámara) para tus diapositivas.

## Reglas implementadas
- **RN-01 (adaptada):** columnas obligatorias: Documento, Edad, Especialidad, Fecha de Ingreso, Ha venido antes.
- **RN-02:** ≥ 3 inasistencias injustificadas en 6 meses (ventana móvil; parámetros editables en *Parámetros de métricas*).
- **RN-03:** Analista (cargas, historial, parámetros) · Administrador (reportes, auditoría, usuarios). Se cambia en `PERMISOS` de `eps/config.py`.
