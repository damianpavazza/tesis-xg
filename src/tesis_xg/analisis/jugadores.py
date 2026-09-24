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
