from __future__ import annotations

import sqlite3

import pandas as pd


def porcentaje_victorias_segun_xg_y_ppda(
    conexion: sqlite3.Connection,
    codigo_liga: str | None = None,
    temporada: int | None = None,
) -> pd.DataFrame:
    """Porcentaje de victorias por encima/por debajo de la media de xG y
    de ppda (sección 7). La liga y la temporada son parámetros opcionales
    para acotar el universo sobre el que se calcula la media."""
    condiciones = []
    parametros: dict[str, object] = {}
    if codigo_liga is not None:
        condiciones.append("l.codigo = :codigo_liga")
        parametros["codigo_liga"] = codigo_liga
    if temporada is not None:
        condiciones.append("t.anio_inicio = :temporada")
        parametros["temporada"] = temporada
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    consulta = f"""
        SELECT ep.xg, ep.ppda_coef, ep.resultado
        FROM equipo_partido ep
        JOIN partido p ON p.id = ep.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        JOIN liga l ON l.id = t.liga_id
        {where}
    """
    df = pd.read_sql_query(consulta, conexion, params=parametros)
    df["es_victoria"] = (df["resultado"] == "w").astype(int)

    filas = []
    for columna, etiqueta in (("xg", "xG"), ("ppda_coef", "ppda")):
        valido = df.dropna(subset=[columna])
        media = valido[columna].mean()
        for grupo, mascara in (
            ("por encima de la media", valido[columna] > media),
            ("por debajo de la media", valido[columna] <= media),
        ):
            subconjunto = valido[mascara]
            filas.append(
                {
                    "variable": etiqueta,
                    "grupo": grupo,
                    "media": media,
                    "porcentaje_victorias": subconjunto["es_victoria"].mean() if len(subconjunto) else None,
                    "n": len(subconjunto),
                }
            )
    return pd.DataFrame(filas)


def disparos_de_partido(conexion: sqlite3.Connection, partido_id: int) -> pd.DataFrame:
    """Disparos de un partido con su ubicación, para el mapa de disparos
    del dashboard (sección 7 / 8)."""
    consulta = """
        SELECT d.id, d.equipo_id, e.nombre AS equipo, d.jugador_id, j.nombre AS jugador,
               d.minuto, d.x, d.y, d.resultado, d.es_gol, d.xg_understat, d.xg_propio
        FROM disparo d
        JOIN equipo e ON e.id = d.equipo_id
        LEFT JOIN jugador j ON j.id = d.jugador_id
        WHERE d.partido_id = :partido_id
        ORDER BY d.minuto
    """
    return pd.read_sql_query(consulta, conexion, params={"partido_id": partido_id})


def linea_tiempo_xg_partido(conexion: sqlite3.Connection, partido_id: int) -> pd.DataFrame:
    """xG acumulado de cada equipo minuto a minuto (sección 7/8)."""
    disparos = disparos_de_partido(conexion, partido_id).sort_values("minuto")
    disparos["xg_acumulado"] = disparos.groupby("equipo_id")["xg_understat"].cumsum()
    return disparos[["minuto", "equipo_id", "equipo", "xg_understat", "xg_acumulado"]].reset_index(drop=True)


def evolucion_equipo_por_temporada(conexion: sqlite3.Connection, equipo_id: int) -> pd.DataFrame:
    """Evolución de xG, xGA y ppda de un equipo a lo largo de las
    temporadas en las que jugó. No está entre las funciones que pide la
    sección 7 (que solo cubre el top-5 de xG/xGA), pero la vista
    "Equipo" del dashboard (sección 8) la necesita para un equipo
    cualquiera, no solo para los mejores cinco."""
    consulta = """
        SELECT
            t.anio_inicio AS temporada,
            SUM(ep.xg) AS xg,
            SUM(ep.xga) AS xga,
            AVG(ep.ppda_coef) AS ppda_coef
        FROM equipo_partido ep
        JOIN partido p ON p.id = ep.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        WHERE ep.equipo_id = :equipo_id
        GROUP BY t.anio_inicio
        ORDER BY t.anio_inicio
    """
    return pd.read_sql_query(consulta, conexion, params={"equipo_id": equipo_id})
