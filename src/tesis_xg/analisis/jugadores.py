from __future__ import annotations

import sqlite3

import pandas as pd


def goles_vs_xg_por_jugador(
    conexion: sqlite3.Connection, temporada: int, minutos_minimos: int = 900
) -> pd.DataFrame:
    """Goles contra xG por jugador, para una temporada, filtrando por
    minutos jugados mínimos (sección 7).

    `xg_understat` es el agregado oficial de la temporada (de
    `jugador_temporada`, que viene de `getLeagueData`); `xg_propio` se
    recalcula sumando `disparo.xg_propio` de esa misma temporada, para
    poder comparar ambos.

    Nota: la especificación también pide "distribución del xG por edad
    de los ejecutantes", que no se implementó — Understat no expone
    edad ni fecha de nacimiento en ningún endpoint (ver DESVIACIONES.md,
    Etapa 8).
    """
    consulta = """
        WITH xg_propio_temporada AS (
            SELECT d.jugador_id, p.temporada_id, SUM(d.xg_propio) AS xg_propio
            FROM disparo d
            JOIN partido p ON p.id = d.partido_id
            GROUP BY d.jugador_id, p.temporada_id
        )
        SELECT
            j.id AS jugador_id, j.nombre, jt.equipo, jt.minutos, jt.partidos,
            jt.goles, jt.goles_np, jt.xg AS xg_understat,
            COALESCE(xpt.xg_propio, 0) AS xg_propio,
            (jt.goles - jt.xg) AS goles_menos_xg
        FROM jugador_temporada jt
        JOIN jugador j ON j.id = jt.jugador_id
        JOIN temporada t ON t.id = jt.temporada_id
        LEFT JOIN xg_propio_temporada xpt
            ON xpt.jugador_id = jt.jugador_id AND xpt.temporada_id = jt.temporada_id
        WHERE t.anio_inicio = :temporada AND jt.minutos >= :minutos_minimos
        ORDER BY goles_menos_xg DESC
    """
    return pd.read_sql_query(
        consulta, conexion, params={"temporada": temporada, "minutos_minimos": minutos_minimos}
    )


def evolucion_jugador(conexion: sqlite3.Connection, jugador_id: int) -> pd.DataFrame:
    """Goles y xG de un jugador a lo largo de las temporadas en las que
    jugó. Tampoco está entre las funciones de la sección 7 (que agrupa
    por temporada para TODOS los jugadores, no la evolución de uno
    puntual), pero la vista "Jugador" del dashboard (sección 8) la
    necesita: "goles contra xG **por temporada**" para un jugador."""
    consulta = """
        SELECT t.anio_inicio AS temporada, jt.equipo, jt.minutos,
               jt.goles, jt.xg AS xg_understat
        FROM jugador_temporada jt
        JOIN temporada t ON t.id = jt.temporada_id
        WHERE jt.jugador_id = :jugador_id
        ORDER BY t.anio_inicio
    """
    return pd.read_sql_query(consulta, conexion, params={"jugador_id": jugador_id})


def disparos_de_jugador(
    conexion: sqlite3.Connection, jugador_id: int, temporada: int | None = None
) -> pd.DataFrame:
    """Disparos de un jugador (todas las temporadas, o una puntual), para
    el mapa de disparos de la vista "Jugador" del dashboard."""
    condicion = ""
    parametros: dict[str, object] = {"jugador_id": jugador_id}
    if temporada is not None:
        condicion = "AND t.anio_inicio = :temporada"
        parametros["temporada"] = temporada

    consulta = f"""
        SELECT d.id, d.partido_id, d.minuto, d.x, d.y, d.resultado, d.es_gol,
               d.xg_understat, d.xg_propio
        FROM disparo d
        JOIN partido p ON p.id = d.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        WHERE d.jugador_id = :jugador_id {condicion}
        ORDER BY p.fecha, d.minuto
    """
    return pd.read_sql_query(consulta, conexion, params=parametros)


def buscar_jugadores(
    conexion: sqlite3.Connection, codigo_liga: str | None = None, temporada: int | None = None
) -> pd.DataFrame:
    """Jugadores para el buscador de la vista "Jugador" del dashboard.

    Sin parámetros devuelve todos. `codigo_liga` y `temporada` solo
    acotan *quién aparece* en la búsqueda (jugadores que jugaron en esa
    liga y/o temporada): el rango `desde`-`hasta` y el `equipo` siempre
    corresponden a toda su carrera, no al filtro. `equipo` es el de su
    última temporada, para distinguir homónimos.
    """
    consulta = """
        WITH rangos AS (
            SELECT jt.jugador_id, MIN(t.anio_inicio) AS desde, MAX(t.anio_inicio) AS hasta
            FROM jugador_temporada jt
            JOIN temporada t ON t.id = jt.temporada_id
            GROUP BY jt.jugador_id
        ),
        ultimo AS (
            SELECT jt.jugador_id, jt.equipo,
                   ROW_NUMBER() OVER (
                       PARTITION BY jt.jugador_id ORDER BY t.anio_inicio DESC
                   ) AS orden
            FROM jugador_temporada jt
            JOIN temporada t ON t.id = jt.temporada_id
        )
        SELECT j.id AS jugador_id, j.nombre, r.desde, r.hasta, u.equipo
        FROM jugador j
        JOIN rangos r ON r.jugador_id = j.id
        JOIN ultimo u ON u.jugador_id = j.id AND u.orden = 1
        WHERE j.id IN (
            SELECT jt.jugador_id
            FROM jugador_temporada jt
            JOIN temporada t ON t.id = jt.temporada_id
            JOIN liga l ON l.id = t.liga_id
            WHERE (:codigo_liga IS NULL OR l.codigo = :codigo_liga)
              AND (:temporada IS NULL OR t.anio_inicio = :temporada)
        )
        ORDER BY j.nombre, j.id
    """
    return pd.read_sql_query(
        consulta, conexion, params={"codigo_liga": codigo_liga, "temporada": temporada}
    )
