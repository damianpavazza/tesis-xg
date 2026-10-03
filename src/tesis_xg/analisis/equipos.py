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


def goles_de_partido(conexion: sqlite3.Connection, partido_id: int) -> pd.DataFrame:
    """Goles del partido en orden, con el marcador después de cada uno, para
    marcarlos en la línea de tiempo. Un gol en contra figura como disparo del
    equipo que lo cometió: se asigna al rival, que es a quien le suma."""
    partido = conexion.execute(
        "SELECT equipo_local_id, equipo_visitante_id FROM partido WHERE id = ?", (partido_id,)
    ).fetchone()
    if partido is None:
        return pd.DataFrame(columns=["minuto", "equipo_id", "jugador", "en_contra", "goles_local", "goles_visitante"])
    local_id, visitante_id = partido
    consulta = """
        SELECT d.minuto, d.equipo_id, j.nombre AS jugador, d.resultado = 'OwnGoal' AS en_contra
        FROM disparo d
        LEFT JOIN jugador j ON j.id = d.jugador_id
        WHERE d.partido_id = :partido_id AND d.resultado IN ('Goal', 'OwnGoal')
        ORDER BY d.minuto, d.id
    """
    goles = pd.read_sql_query(consulta, conexion, params={"partido_id": partido_id})
    goles["en_contra"] = goles["en_contra"].astype(bool)
    rival = {local_id: visitante_id, visitante_id: local_id}
    goles["equipo_id"] = [rival[e] if en_contra else e for e, en_contra in zip(goles["equipo_id"], goles["en_contra"])]
    goles["goles_local"] = (goles["equipo_id"] == local_id).cumsum()
    goles["goles_visitante"] = (goles["equipo_id"] == visitante_id).cumsum()
    return goles


def estadisticas_de_partido(conexion: sqlite3.Connection, partido_id: int) -> pd.DataFrame:
    """Comparativa de los dos equipos de un partido (pestaña de estadísticas),
    con el local primero. Los tiros al arco son los goles y los disparos
    atajados, como los cuenta Understat."""
    consulta = """
        SELECT ep.equipo_id, e.nombre AS equipo, ep.condicion, ep.goles, ep.xg,
               COUNT(d.id) AS tiros,
               COALESCE(SUM(d.resultado IN ('Goal', 'SavedShot')), 0) AS tiros_al_arco,
               ep.deep, ep.ppda_coef AS ppda, ep.xpts
        FROM equipo_partido ep
        JOIN equipo e ON e.id = ep.equipo_id
        LEFT JOIN disparo d ON d.partido_id = ep.partido_id AND d.equipo_id = ep.equipo_id
        WHERE ep.partido_id = :partido_id
        GROUP BY ep.equipo_id
        ORDER BY ep.condicion DESC
    """
    return pd.read_sql_query(consulta, conexion, params={"partido_id": partido_id})


def filtrar_partidos(partidos: pd.DataFrame, equipo_a: str | None, equipo_b: str | None) -> pd.DataFrame:
    """Partidos de un equipo, o los que enfrentan a dos. Sin equipos devuelve
    todos. Con un solo equipo no importa cuál de los dos filtros se use."""
    elegidos = [e for e in (equipo_a, equipo_b) if e]
    if not elegidos:
        return partidos
    juega = {e: (partidos["local"] == e) | (partidos["visitante"] == e) for e in elegidos}
    mascara = juega[elegidos[0]]
    for e in elegidos[1:]:
        mascara = mascara & juega[e]
    return partidos[mascara]


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
