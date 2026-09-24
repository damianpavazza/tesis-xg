from __future__ import annotations

import sqlite3

import pandas as pd


def evolucion_xg_top5(conexion: sqlite3.Connection, codigo_liga: str) -> pd.DataFrame:
    """Evolución de xG/xGA de los 5 primeros de cada temporada (sección 7).

    "Primeros cinco" se define por la tabla real (suma de puntos), no
    por xPTS. Una fila por (temporada, equipo).
    """
    consulta = """
        WITH agregados AS (
            SELECT
                ep.equipo_id, p.temporada_id, e.nombre AS equipo,
                SUM(ep.puntos) AS puntos, SUM(ep.xg) AS xg, SUM(ep.xga) AS xga
            FROM equipo_partido ep
            JOIN partido p ON p.id = ep.partido_id
            JOIN equipo e ON e.id = ep.equipo_id
            GROUP BY ep.equipo_id, p.temporada_id
        ),
        rankeado AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY temporada_id ORDER BY puntos DESC
            ) AS posicion
            FROM agregados
        )
        SELECT t.anio_inicio AS temporada, r.posicion, r.equipo,
               r.puntos, r.xg, r.xga
        FROM rankeado r
        JOIN temporada t ON t.id = r.temporada_id
        JOIN liga l ON l.id = t.liga_id
        WHERE l.codigo = :codigo_liga AND r.posicion <= 5
        ORDER BY t.anio_inicio, r.posicion
    """
    return pd.read_sql_query(consulta, conexion, params={"codigo_liga": codigo_liga})


def tabla_posiciones_vs_xpts(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> pd.DataFrame:
    """Tabla de posiciones real (por puntos) contra la ordenada por xPTS
    acumulados, para una liga y temporada puntuales (sección 7)."""
    consulta = """
        SELECT ep.equipo_id, e.nombre AS equipo,
               SUM(ep.puntos) AS puntos, SUM(ep.xpts) AS xpts
        FROM equipo_partido ep
        JOIN partido p ON p.id = ep.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        JOIN liga l ON l.id = t.liga_id
        JOIN equipo e ON e.id = ep.equipo_id
        WHERE l.codigo = :codigo_liga AND t.anio_inicio = :temporada
        GROUP BY ep.equipo_id
    """
    df = pd.read_sql_query(consulta, conexion, params={"codigo_liga": codigo_liga, "temporada": temporada})

    df["posicion_real"] = df["puntos"].rank(ascending=False, method="min").astype(int)
    df["posicion_xpts"] = df["xpts"].rank(ascending=False, method="min").astype(int)
    df["diferencia_posicion"] = df["posicion_real"] - df["posicion_xpts"]

    columnas = ["equipo", "puntos", "posicion_real", "xpts", "posicion_xpts", "diferencia_posicion"]
    return df[columnas].sort_values("posicion_real").reset_index(drop=True)
