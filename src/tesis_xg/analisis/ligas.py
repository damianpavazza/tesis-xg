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


# Ligas que desempatan primero por enfrentamiento directo (mini-tabla entre
# los equipos igualados) y recién después por diferencia de gol. En las
# otras (EPL, Bundesliga, Ligue 1) el criterio es diferencia de gol y luego
# goles a favor.
LIGAS_CON_ENFRENTAMIENTO_DIRECTO = {"La_liga", "Serie_A"}


def _desempatar(grupo: pd.DataFrame, partidos: pd.DataFrame, con_enfrentamiento_directo: bool) -> pd.DataFrame:
    """Ordena un grupo de equipos con los mismos puntos."""
    grupo = grupo.copy()
    grupo["dir_puntos"] = 0
    grupo["dir_dg"] = 0

    if con_enfrentamiento_directo and len(grupo) > 1:
        ids = set(grupo["equipo_id"])
        cruces = partidos[partidos["equipo_local_id"].isin(ids) & partidos["equipo_visitante_id"].isin(ids)]
        puntos = dict.fromkeys(ids, 0)
        dg = dict.fromkeys(ids, 0)
        for cruce in cruces.itertuples():
            local, visitante = cruce.equipo_local_id, cruce.equipo_visitante_id
            dg[local] += cruce.goles_local - cruce.goles_visitante
            dg[visitante] += cruce.goles_visitante - cruce.goles_local
            if cruce.goles_local > cruce.goles_visitante:
                puntos[local] += 3
            elif cruce.goles_local < cruce.goles_visitante:
                puntos[visitante] += 3
            else:
                puntos[local] += 1
                puntos[visitante] += 1
        grupo["dir_puntos"] = grupo["equipo_id"].map(puntos)
        grupo["dir_dg"] = grupo["equipo_id"].map(dg)

    return grupo.sort_values(
        ["dir_puntos", "dir_dg", "dg", "g", "equipo"],
        ascending=[False, False, False, False, True],
    )


def tabla_posiciones_vs_xpts(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> pd.DataFrame:
    """Tabla de posiciones real contra la ordenada por xPTS acumulados,
    para una liga y temporada puntuales (sección 7).

    La posición real nunca se repite: los equipos con los mismos puntos se
    desempatan según el reglamento de la liga (ver
    `LIGAS_CON_ENFRENTAMIENTO_DIRECTO`). Las columnas `dif_*` siguen la
    convención de Understat (esperado − real): negativo en xG y xPTS, o
    positivo en xGA, significa que el equipo rindió por encima de lo
    esperado.
    """
    parametros = {"codigo_liga": codigo_liga, "temporada": temporada}
    consulta = """
        SELECT ep.equipo_id, e.nombre AS equipo,
               COUNT(*) AS pj,
               SUM(ep.resultado = 'w') AS pg,
               SUM(ep.resultado = 'd') AS pe,
               SUM(ep.resultado = 'l') AS pp,
               SUM(ep.goles) AS g, SUM(ep.goles_recibidos) AS ga,
               SUM(ep.puntos) AS puntos,
               SUM(ep.xg) AS xg, SUM(ep.xga) AS xga, SUM(ep.xpts) AS xpts
        FROM equipo_partido ep
        JOIN partido p ON p.id = ep.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        JOIN liga l ON l.id = t.liga_id
        JOIN equipo e ON e.id = ep.equipo_id
        WHERE l.codigo = :codigo_liga AND t.anio_inicio = :temporada
        GROUP BY ep.equipo_id
    """
    df = pd.read_sql_query(consulta, conexion, params=parametros)
    df["dg"] = df["g"] - df["ga"]

    partidos = pd.read_sql_query(
        """
        SELECT p.equipo_local_id, p.equipo_visitante_id, p.goles_local, p.goles_visitante
        FROM partido p
        JOIN temporada t ON t.id = p.temporada_id
        JOIN liga l ON l.id = t.liga_id
        WHERE l.codigo = :codigo_liga AND t.anio_inicio = :temporada
        """,
        conexion,
        params=parametros,
    )

    con_enfrentamiento_directo = codigo_liga in LIGAS_CON_ENFRENTAMIENTO_DIRECTO
    grupos = [
        _desempatar(grupo, partidos, con_enfrentamiento_directo)
        for _, grupo in sorted(df.groupby("puntos"), key=lambda par: par[0], reverse=True)
    ]
    df = pd.concat(grupos).reset_index(drop=True)

    df["posicion_real"] = range(1, len(df) + 1)
    df["posicion_xpts"] = df["xpts"].rank(ascending=False, method="first").astype(int)
    df["diferencia_posicion"] = df["posicion_real"] - df["posicion_xpts"]

    df["dif_xg"] = df["xg"] - df["g"]
    df["dif_xga"] = df["xga"] - df["ga"]
    df["dif_xpts"] = df["xpts"] - df["puntos"]

    columnas = [
        "posicion_real", "equipo", "pj", "pg", "pe", "pp", "g", "ga", "dg", "puntos",
        "xg", "dif_xg", "xga", "dif_xga", "xpts", "dif_xpts",
        "posicion_xpts", "diferencia_posicion",
    ]
    return df[columnas]
