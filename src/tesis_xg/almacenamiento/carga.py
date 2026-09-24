from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Understat no informa nombre/país de la liga en ningún endpoint: solo el
# código con el que se pide (EPL, La_liga, ...). Se fija acá porque el
# esquema exige liga.nombre y liga.pais como NOT NULL.
LIGAS_INFO: dict[str, tuple[str, str]] = {
    "EPL": ("Premier League", "Inglaterra"),
    "La_liga": ("La Liga", "España"),
    "Serie_A": ("Serie A", "Italia"),
    "Bundesliga": ("Bundesliga", "Alemania"),
    "Ligue_1": ("Ligue 1", "Francia"),
}

_RE_CACHE_LIGA = re.compile(r"^liga_(?P<codigo>.+)_(?P<temporada>\d{4})\.json$")
_RE_CACHE_PARTIDO = re.compile(r"^partido_(?P<id>\d+)\.json$")


def _normalizar_fecha(fecha: str) -> str:
    iso = fecha.replace(" ", "T", 1)
    datetime.fromisoformat(iso)  # valida el formato
    return iso


def _leer_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf8"))


# --- upserts -----------------------------------------------------------


def _upsert_liga(conexion: sqlite3.Connection, codigo: str) -> int:
    nombre, pais = LIGAS_INFO.get(codigo, (codigo, "Desconocido"))
    if codigo not in LIGAS_INFO:
        logger.warning("liga %s sin nombre/país conocido, se usan valores provisorios", codigo)

    conexion.execute(
        """
        INSERT INTO liga (codigo, nombre, pais) VALUES (?, ?, ?)
        ON CONFLICT (codigo) DO UPDATE SET nombre = excluded.nombre, pais = excluded.pais
        """,
        (codigo, nombre, pais),
    )
    fila = conexion.execute("SELECT id FROM liga WHERE codigo = ?", (codigo,)).fetchone()
    return fila["id"]


def _upsert_temporada(conexion: sqlite3.Connection, liga_id: int, anio_inicio: int) -> int:
    conexion.execute(
        """
        INSERT INTO temporada (liga_id, anio_inicio) VALUES (?, ?)
        ON CONFLICT (liga_id, anio_inicio) DO UPDATE SET anio_inicio = excluded.anio_inicio
        """,
        (liga_id, anio_inicio),
    )
    fila = conexion.execute(
        "SELECT id FROM temporada WHERE liga_id = ? AND anio_inicio = ?",
        (liga_id, anio_inicio),
    ).fetchone()
    return fila["id"]


def _upsert_equipo(conexion: sqlite3.Connection, equipo_id: int, nombre: str) -> None:
    conexion.execute(
        """
        INSERT INTO equipo (id, nombre) VALUES (?, ?)
        ON CONFLICT (id) DO UPDATE SET nombre = excluded.nombre
        """,
        (equipo_id, nombre),
    )


def _upsert_jugador(conexion: sqlite3.Connection, jugador_id: int, nombre: str) -> None:
    conexion.execute(
        """
        INSERT INTO jugador (id, nombre) VALUES (?, ?)
        ON CONFLICT (id) DO UPDATE SET nombre = excluded.nombre
        """,
        (jugador_id, nombre),
    )


def _upsert_jugador_temporada(conexion: sqlite3.Connection, fila: dict) -> None:
    conexion.execute(
        """
        INSERT INTO jugador_temporada
            (jugador_id, temporada_id, equipo, posicion, partidos, minutos,
             goles, goles_np, asistencias, xg, xg_np, xa, disparos, pases_clave)
        VALUES
            (:jugador_id, :temporada_id, :equipo, :posicion, :partidos, :minutos,
             :goles, :goles_np, :asistencias, :xg, :xg_np, :xa, :disparos, :pases_clave)
        ON CONFLICT (jugador_id, temporada_id) DO UPDATE SET
            equipo = excluded.equipo, posicion = excluded.posicion,
            partidos = excluded.partidos, minutos = excluded.minutos,
            goles = excluded.goles, goles_np = excluded.goles_np,
            asistencias = excluded.asistencias, xg = excluded.xg,
            xg_np = excluded.xg_np, xa = excluded.xa,
            disparos = excluded.disparos, pases_clave = excluded.pases_clave
        """,
        fila,
    )


def _upsert_partido(conexion: sqlite3.Connection, partido: dict) -> None:
    conexion.execute(
        """
        INSERT INTO partido
            (id, temporada_id, fecha, equipo_local_id, equipo_visitante_id, goles_local, goles_visitante)
        VALUES (:id, :temporada_id, :fecha, :equipo_local_id, :equipo_visitante_id, :goles_local, :goles_visitante)
        ON CONFLICT (id) DO UPDATE SET
            temporada_id = excluded.temporada_id,
            fecha = excluded.fecha,
            equipo_local_id = excluded.equipo_local_id,
            equipo_visitante_id = excluded.equipo_visitante_id,
            goles_local = excluded.goles_local,
            goles_visitante = excluded.goles_visitante
        """,
        partido,
    )


def _upsert_equipo_partido(conexion: sqlite3.Connection, fila: dict) -> None:
    conexion.execute(
        """
        INSERT INTO equipo_partido
            (partido_id, equipo_id, condicion, xg, xga, npxg, npxga, npxgd,
             ppda_att, ppda_def, ppda_coef, oppda_att, oppda_def, oppda_coef,
             deep, deep_allowed, goles, goles_recibidos, xpts, puntos, resultado)
        VALUES
            (:partido_id, :equipo_id, :condicion, :xg, :xga, :npxg, :npxga, :npxgd,
             :ppda_att, :ppda_def, :ppda_coef, :oppda_att, :oppda_def, :oppda_coef,
             :deep, :deep_allowed, :goles, :goles_recibidos, :xpts, :puntos, :resultado)
        ON CONFLICT (partido_id, equipo_id) DO UPDATE SET
            condicion = excluded.condicion, xg = excluded.xg, xga = excluded.xga,
            npxg = excluded.npxg, npxga = excluded.npxga, npxgd = excluded.npxgd,
            ppda_att = excluded.ppda_att, ppda_def = excluded.ppda_def, ppda_coef = excluded.ppda_coef,
            oppda_att = excluded.oppda_att, oppda_def = excluded.oppda_def, oppda_coef = excluded.oppda_coef,
            deep = excluded.deep, deep_allowed = excluded.deep_allowed,
            goles = excluded.goles, goles_recibidos = excluded.goles_recibidos,
            xpts = excluded.xpts, puntos = excluded.puntos, resultado = excluded.resultado
        """,
        fila,
    )


def _upsert_disparo(conexion: sqlite3.Connection, fila: dict) -> None:
    # distancia, angulo y xg_propio no se tocan: los completan las etapas
    # 5 y 7. Si se los incluyera en el UPDATE, recargar la base desde la
    # caché borraría ese trabajo.
    conexion.execute(
        """
        INSERT INTO disparo
            (id, partido_id, equipo_id, jugador_id, jugador_asistencia_id, minuto, x, y,
             resultado, situacion, tipo_disparo, accion_previa, es_gol, xg_understat)
        VALUES
            (:id, :partido_id, :equipo_id, :jugador_id, :jugador_asistencia_id, :minuto, :x, :y,
             :resultado, :situacion, :tipo_disparo, :accion_previa, :es_gol, :xg_understat)
        ON CONFLICT (id) DO UPDATE SET
            partido_id = excluded.partido_id, equipo_id = excluded.equipo_id,
            jugador_id = excluded.jugador_id, jugador_asistencia_id = excluded.jugador_asistencia_id,
            minuto = excluded.minuto, x = excluded.x, y = excluded.y,
            resultado = excluded.resultado, situacion = excluded.situacion,
            tipo_disparo = excluded.tipo_disparo, accion_previa = excluded.accion_previa,
            es_gol = excluded.es_gol, xg_understat = excluded.xg_understat
        """,
        fila,
    )


# --- transformación ------------------------------------------------------


def _cargar_liga_json(conexion: sqlite3.Connection, codigo: str, temporada: int, datos: dict) -> None:
    liga_id = _upsert_liga(conexion, codigo)
    temporada_id = _upsert_temporada(conexion, liga_id, temporada)

    for equipo in datos["teams"].values():
        _upsert_equipo(conexion, int(equipo["id"]), equipo["title"])

    for jugador in datos["players"]:
        jugador_id = int(jugador["id"])
        _upsert_jugador(conexion, jugador_id, jugador["player_name"])
        _upsert_jugador_temporada(
            conexion,
            {
                "jugador_id": jugador_id,
                "temporada_id": temporada_id,
                "equipo": jugador["team_title"],
                "posicion": jugador["position"],
                "partidos": int(jugador["games"]),
                "minutos": int(jugador["time"]),
                "goles": int(jugador["goals"]),
                "goles_np": int(jugador["npg"]),
                "asistencias": int(jugador["assists"]),
                "xg": float(jugador["xG"]),
                "xg_np": float(jugador["npxG"]),
                "xa": float(jugador["xA"]),
                "disparos": int(jugador["shots"]),
                "pases_clave": int(jugador["key_passes"]),
            },
        )

    # teams[*].history no trae el id de partido, solo la fecha: se cruza
    # por (equipo, fecha) contra datesData para reconstruir equipo_partido.
    historial: dict[tuple[int, str], dict] = {}
    for equipo in datos["teams"].values():
        equipo_id = int(equipo["id"])
        for entrada in equipo["history"]:
            historial[(equipo_id, entrada["date"])] = entrada

    partidos_jugados = [p for p in datos["dates"] if p["isResult"]]
    for partido in partidos_jugados:
        partido_id = int(partido["id"])
        local_id = int(partido["h"]["id"])
        visitante_id = int(partido["a"]["id"])
        fecha = _normalizar_fecha(partido["datetime"])

        _upsert_partido(
            conexion,
            {
                "id": partido_id,
                "temporada_id": temporada_id,
                "fecha": fecha,
                "equipo_local_id": local_id,
                "equipo_visitante_id": visitante_id,
                "goles_local": int(partido["goals"]["h"]),
                "goles_visitante": int(partido["goals"]["a"]),
            },
        )

        for equipo_id in (local_id, visitante_id):
            entrada = historial.get((equipo_id, partido["datetime"]))
            if entrada is None:
                logger.warning(
                    "sin historial de equipo %d para el partido %d (%s)",
                    equipo_id, partido_id, partido["datetime"],
                )
                continue

            ppda_att, ppda_def = entrada["ppda"]["att"], entrada["ppda"]["def"]
            oppda_att, oppda_def = entrada["ppda_allowed"]["att"], entrada["ppda_allowed"]["def"]

            _upsert_equipo_partido(
                conexion,
                {
                    "partido_id": partido_id,
                    "equipo_id": equipo_id,
                    "condicion": entrada["h_a"],
                    "xg": entrada["xG"],
                    "xga": entrada["xGA"],
                    "npxg": entrada["npxG"],
                    "npxga": entrada["npxGA"],
                    "npxgd": entrada["npxGD"],
                    "ppda_att": ppda_att,
                    "ppda_def": ppda_def,
                    "ppda_coef": (ppda_att / ppda_def) if ppda_def else None,
                    "oppda_att": oppda_att,
                    "oppda_def": oppda_def,
                    "oppda_coef": (oppda_att / oppda_def) if oppda_def else None,
                    "deep": entrada["deep"],
                    "deep_allowed": entrada["deep_allowed"],
                    "goles": entrada["scored"],
                    "goles_recibidos": entrada["missed"],
                    "xpts": entrada["xpts"],
                    "puntos": entrada["pts"],
                    "resultado": entrada["result"],
                },
            )


def _cargar_partido_json(conexion: sqlite3.Connection, partido_id: int, datos: dict) -> None:
    fila_partido = conexion.execute(
        "SELECT equipo_local_id, equipo_visitante_id FROM partido WHERE id = ?",
        (partido_id,),
    ).fetchone()
    if fila_partido is None:
        logger.warning(
            "partido %d en caché pero ausente en la tabla partido "
            "(¿falta cargar la liga/temporada correspondiente?); se omite",
            partido_id,
        )
        return

    equipo_por_lado = {
        "h": fila_partido["equipo_local_id"],
        "a": fila_partido["equipo_visitante_id"],
    }

    # player_assisted trae el NOMBRE del jugador, no su id (punto "a
    # verificar" del documento). Se resuelve contra el roster de este
    # mismo partido: acota la búsqueda al universo correcto de 22
    # jugadores y evita colisiones de nombre entre partidos distintos.
    nombre_a_id: dict[str, int] = {}
    for lado in ("h", "a"):
        roster_lado = datos["rosters"][lado]
        # Understat normalmente devuelve un objeto {player_id: {...}}, pero
        # cuando no tiene datos de alineacion para el partido devuelve una
        # lista vacia en su lugar (visto en partidos historicos puntuales).
        jugadores_del_lado = roster_lado.values() if isinstance(roster_lado, dict) else roster_lado
        for jugador in jugadores_del_lado:
            jugador_id = int(jugador["player_id"])
            _upsert_jugador(conexion, jugador_id, jugador["player"])
            nombre_a_id[jugador["player"]] = jugador_id

    for lado in ("h", "a"):
        for disparo in datos["shots"][lado]:
            jugador_asistencia_id = None
            nombre_asistencia = disparo.get("player_assisted")
            if nombre_asistencia:
                jugador_asistencia_id = nombre_a_id.get(nombre_asistencia)
                if jugador_asistencia_id is None:
                    logger.warning(
                        "asistencia de '%s' no encontrada en el roster del partido %d",
                        nombre_asistencia, partido_id,
                    )

            _upsert_disparo(
                conexion,
                {
                    "id": int(disparo["id"]),
                    "partido_id": partido_id,
                    "equipo_id": equipo_por_lado[disparo["h_a"]],
                    "jugador_id": int(disparo["player_id"]),
                    "jugador_asistencia_id": jugador_asistencia_id,
                    "minuto": int(disparo["minute"]),
                    "x": float(disparo["X"]),
                    "y": float(disparo["Y"]),
                    "resultado": disparo["result"],
                    "situacion": disparo["situation"],
                    "tipo_disparo": disparo["shotType"],
                    # "None" es una categoria valida (sin accion previa),
                    # no se convierte a NULL.
                    "accion_previa": disparo["lastAction"],
                    "es_gol": 1 if disparo["result"] == "Goal" else 0,
                    "xg_understat": float(disparo["xG"]),
                },
            )


def cargar_todo(conexion: sqlite3.Connection, directorio_cache: Path) -> None:
    """Reconstruye la base entera a partir de lo que haya en la caché, sin red."""
    directorio_cache = Path(directorio_cache)

    archivos_liga = sorted(directorio_cache.glob("liga_*.json"))
    for ruta in archivos_liga:
        coincidencia = _RE_CACHE_LIGA.match(ruta.name)
        if not coincidencia:
            continue
        codigo = coincidencia["codigo"]
        temporada = int(coincidencia["temporada"])
        logger.info("cargando liga %s %s desde %s", codigo, temporada, ruta.name)
        _cargar_liga_json(conexion, codigo, temporada, _leer_json(ruta))
        conexion.commit()

    archivos_partido = sorted(directorio_cache.glob("partido_*.json"))
    for ruta in archivos_partido:
        coincidencia = _RE_CACHE_PARTIDO.match(ruta.name)
        if not coincidencia:
            continue
        partido_id = int(coincidencia["id"])
        _cargar_partido_json(conexion, partido_id, _leer_json(ruta))
        conexion.commit()

    logger.info(
        "carga terminada: %d archivo(s) de liga, %d archivo(s) de partido",
        len(archivos_liga), len(archivos_partido),
    )


# --- validación posterior a la carga --------------------------------------


def informe_validacion(conexion: sqlite3.Connection) -> str:
    lineas: list[str] = []

    lineas.append("Partidos por liga y temporada:")
    for fila in conexion.execute(
        """
        SELECT l.codigo, t.anio_inicio, COUNT(*) AS n
        FROM partido p
        JOIN temporada t ON t.id = p.temporada_id
        JOIN liga l ON l.id = t.liga_id
        GROUP BY l.codigo, t.anio_inicio
        ORDER BY l.codigo, t.anio_inicio
        """
    ):
        lineas.append(f"  {fila['codigo']} {fila['anio_inicio']}: {fila['n']}")

    (total_disparos,) = conexion.execute("SELECT COUNT(*) FROM disparo").fetchone()
    (total_goles,) = conexion.execute("SELECT SUM(es_gol) FROM disparo").fetchone()
    total_goles = total_goles or 0
    proporcion = (total_goles / total_disparos) if total_disparos else 0.0
    lineas.append(f"\nDisparos totales: {total_disparos}")
    lineas.append(f"Goles: {total_goles} ({proporcion:.2%} de los disparos)")

    lineas.append("\nNulos por columna (disparo):")
    columnas_disparo = [
        "jugador_id", "jugador_asistencia_id", "accion_previa",
        "distancia", "angulo", "xg_propio",
    ]
    for columna in columnas_disparo:
        (n_nulos,) = conexion.execute(
            f"SELECT COUNT(*) FROM disparo WHERE {columna} IS NULL"
        ).fetchone()
        lineas.append(f"  {columna}: {n_nulos}")

    lineas.append("\nNulos por columna (equipo_partido):")
    for columna in ("ppda_coef", "oppda_coef"):
        (n_nulos,) = conexion.execute(
            f"SELECT COUNT(*) FROM equipo_partido WHERE {columna} IS NULL"
        ).fetchone()
        lineas.append(f"  {columna}: {n_nulos}")

    lineas.append("\nValores distintos por campo categórico:")
    for tabla, columna in (
        ("disparo", "resultado"),
        ("disparo", "situacion"),
        ("disparo", "tipo_disparo"),
        ("disparo", "accion_previa"),
        ("equipo_partido", "resultado"),
    ):
        valores = [
            fila[0]
            for fila in conexion.execute(
                f"SELECT DISTINCT {columna} FROM {tabla} ORDER BY {columna}"
            )
        ]
        lineas.append(f"  {tabla}.{columna}: {valores}")

    return "\n".join(lineas)
