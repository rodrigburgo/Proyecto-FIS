# EPS Tracker

Carga archivos de atenciones/citas (CSV o Excel), los valida, los guarda en una base de datos y muestra un
dashboard con filtros, alertas de reincidencia, reportes (Excel/PDF/CSV), auditoría y gestión de usuarios.

## Ejecutar
```bash
py -m pip install -r requirements.txt
py -m streamlit run app.py
```
Abre http://localhost:8501. Usuarios iniciales (**cámbialos** en *Cambiar contraseña*):

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | admin@eps.com | Admin123! |
| Analista de Datos | analista@eps.com | Analista123! |

Flujo: entra como **analista** → *Cargar archivo* → sube tu Excel/CSV → entra como **admin** o analista → *Dashboard*.

## Dashboard con menú de gráficas
Al entrar al Dashboard solo se ven los indicadores (KPIs). Las gráficas se piden a demanda:
- **Vistas rápidas:** Resumen ejecutivo, Reincidencia, Clínico y Ausentismo (un clic).
- **Selección manual:** elige una o varias de las 15 gráficas y pulsa *Generar gráficas*.
- Se puede mostrar 1 o 2 gráficas por fila. Las de ausentismo solo aparecen si la base trae *Estado de la cita*.
- Los filtros de la izquierda se aplican a lo que ya está generado. Solo se consulta la base para las gráficas elegidas.
- Para agregar una gráfica nueva: crea su función en `eps/vistas.py` y añade una línea a `CATALOGO`.

## Datos de prueba con ausentismo
`EPS_Tracker_Database_100k_v3.xlsx` ya trae *Estado de la cita*, *Justificada* y pacientes repetidos (RN-02 completa).
Las citas no atendidas pueden traer `N/A (No asistió)` en los campos clínicos y en *Remitido*: se aceptan y no se grafican.
Para generar más datos sintéticos:
```bash
python generar_datos_prueba.py --filas 300000 --salida datos_prueba.csv
```

## Estructura (MVC + Repository, igual que el informe)
> Los módulos deben estar dentro de la carpeta `eps/` (así los importa `app.py`). Si subes a GitHub, conserva esa carpeta y `.streamlit/`.

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
