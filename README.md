# tesis-xg

Sistema de análisis de datos futbolísticos — componente de ingeniería de
una tesis de grado. Extrae datos de Understat, los almacena en SQLite,
entrena un modelo propio de goles esperados (xG) y expone los análisis
en un dashboard.

El diseño, la implementación y los resultados se describen en la tesis
"Data analytics y fútbol: el aporte de los goles esperados al análisis
del fútbol profesional" (Ingeniería en Informática, Universidad Nacional
de Avellaneda, 2026).

Los datos descargados, la base SQLite y los modelos entrenados no forman
parte del repositorio: se regeneran con los comandos de la sección
[Comandos](#comandos).

## Instalación

Requiere Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Esto crea `data/` y `modelos/` (no se versionan) y deja instalado el
paquete `tesis_xg` en modo editable.

**Problema conocido:** si después de instalar `python -m tesis_xg`
falla con `ModuleNotFoundError: No module named 'tesis_xg'` aunque
`pip show tesis-xg` lo liste como instalado, algún proceso marcó como
"ocultos" los archivos que crea `pip` dentro de `.venv` (flag `hidden`
de macOS) — Python los ignora a propósito. Se soluciona con:

```bash
chflags -R nohidden .venv
```

## Comandos

```bash
# Descarga ligas y partidos de Understat (cachea en data/cache/, reanudable)
python -m tesis_xg descargar --ligas todas --desde 2014 --hasta 2025
python -m tesis_xg descargar --ligas EPL,La_liga --desde 2023 --hasta 2025
python -m tesis_xg descargar                       # usa los valores de config.toml

# Transforma la cache y la persiste en SQLite (no usa red)
python -m tesis_xg cargar

# Calcula variables derivadas (distancia/angulo) y entrena la regresion
# logistica con particion temporal 2014-21 / 2022 / 2023-25
python -m tesis_xg entrenar

# Evalua contra el conjunto de prueba y contra el xG del proveedor;
# persiste modelos/metricas.json
python -m tesis_xg evaluar

# Completa xg_propio en TODA la tabla disparo (no solo el conjunto de
# prueba): no-penales via el modelo, penales via la tasa historica
python -m tesis_xg calcular-xg

# Lanza el dashboard de Streamlit (http://localhost:8501)
python -m tesis_xg dashboard
```

## Módulo de análisis

`src/tesis_xg/analisis/` (`ligas.py`, `equipos.py`, `jugadores.py`)
expone funciones que reciben la conexión y devuelven `DataFrame`, sin
gráficos (eso es responsabilidad del dashboard):

```python
from tesis_xg.almacenamiento import base
from tesis_xg.analisis import ligas, equipos, jugadores

conexion = base.crear("data/tesis.db")
ligas.evolucion_xg_top5(conexion, "EPL")
ligas.tabla_posiciones_vs_xpts(conexion, "EPL", 2024)
equipos.porcentaje_victorias_segun_xg_y_ppda(conexion, codigo_liga="EPL")
equipos.disparos_de_partido(conexion, partido_id=28778)
equipos.linea_tiempo_xg_partido(conexion, partido_id=28778)
jugadores.goles_vs_xg_por_jugador(conexion, temporada=2025, minutos_minimos=1800)
jugadores.resumen_por_temporada(conexion, jugador_id=1250)                    # tabla por temporada (Mohamed Salah)
jugadores.desglose_de_disparos(conexion, 1250, "situacion", temporada=2024)   # o "zona" / "tipo_disparo"
```

## Dashboard

`python -m tesis_xg dashboard` abre las 4 vistas del dashboard (Liga,
Equipo, Jugador y Partido) con selector de liga y temporada en la barra
lateral. La línea de tiempo de xG es una pestaña de la vista Partido, junto con el mapa de disparos y las
estadísticas del partido.

El backfill histórico completo (2014-2025, 5 ligas) ya se corrió una vez
sobre esta base con corte de validación por temporada — ver
`scripts/backfill_historico.py`.

### Descarga: tiempo estimado

`descargar` respeta 1 solicitud por segundo (configurable en
`config.toml`). Medido en esta máquina: descargar los 380 partidos de
una temporada (EPL 2025/2026) tomó **~6 minutos y 40 segundos** en frío.
Con eso, la descarga completa de 5 ligas × 12 temporadas
(≈ 22.000 solicitudes entre ligas y partidos) puede estimarse en
**6 a 8 horas**, corridas una sola vez — las corridas siguientes son
prácticamente instantáneas porque todo queda en caché (`data/cache/`):
repetir el mismo comando sobre datos ya descargados tarda menos de un
segundo. Por eso el proceso está pensado para poder interrumpirse
(Ctrl+C, corte de red) y retomarse sin perder lo ya bajado.

## Licencia

El código se distribuye bajo la licencia MIT (ver `LICENSE`).
