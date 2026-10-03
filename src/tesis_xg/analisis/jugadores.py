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
    el mapa de disparos de la vista "Jugador" del dashboard. Incluye el
    detalle que muestra el tooltip: partido, situación, tipo de disparo y
    quién dio el pase."""
    condicion = ""
    parametros: dict[str, object] = {"jugador_id": jugador_id}
    if temporada is not None:
        condicion = "AND t.anio_inicio = :temporada"
        parametros["temporada"] = temporada

    consulta = f"""
        SELECT d.id, d.partido_id, d.minuto, d.x, d.y, d.resultado, d.es_gol,
               d.situacion, d.tipo_disparo, d.xg_understat, d.xg_propio,
               ja.nombre AS asistente,
               p.fecha, eh.nombre AS local, ea.nombre AS visitante,
               p.goles_local, p.goles_visitante
        FROM disparo d
        JOIN partido p ON p.id = d.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        JOIN equipo eh ON eh.id = p.equipo_local_id
        JOIN equipo ea ON ea.id = p.equipo_visitante_id
        LEFT JOIN jugador ja ON ja.id = d.jugador_asistencia_id
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


# --- Resumen y desglose de un jugador (vista "Jugador" del dashboard) ---------

# Límites de las zonas de tiro, sobre las coordenadas normalizadas (0-1) de
# Understat, que siguen las proporciones de Opta (el punto de penal queda en
# x=0.885) y no las medidas reglamentarias en metros. Se calibraron contra la
# pestaña "Shot zones" de Understat: con estos valores y desigualdades
# estrictas se reproducen exactamente sus conteos para Mohamed Salah
# (270 fuera del área / 930 área grande / 96 área chica).
_X_AREA_GRANDE = 0.83
_Y_AREA_GRANDE = (0.211, 0.789)
_X_AREA_CHICA = 0.942
_Y_AREA_CHICA = (0.368, 0.632)

CATEGORIAS_DESGLOSE = ("situacion", "tipo_disparo", "zona")


def zona_de_tiro(x: pd.Series, y: pd.Series) -> pd.Series:
    """Zona de cada disparo según sus coordenadas normalizadas (0-1, arco
    atacado en x=1): `area_chica`, `area_grande` (sin el área chica) o
    `fuera_del_area`."""
    en_area_chica = (x > _X_AREA_CHICA) & (y > _Y_AREA_CHICA[0]) & (y < _Y_AREA_CHICA[1])
    en_area_grande = (x > _X_AREA_GRANDE) & (y > _Y_AREA_GRANDE[0]) & (y < _Y_AREA_GRANDE[1])
    zona = pd.Series("fuera_del_area", index=x.index)
    zona[en_area_grande] = "area_grande"
    zona[en_area_chica] = "area_chica"
    return zona


def _por_90(valor: pd.Series, minutos: pd.Series) -> pd.Series:
    return (valor / minutos.where(minutos > 0) * 90)


def resumen_por_temporada(conexion: sqlite3.Connection, jugador_id: int, con_total: bool = True) -> pd.DataFrame:
    """Resumen de un jugador por temporada, al estilo de la pestaña "Season"
    de Understat. Una fila por temporada y liga (si cambió de liga a mitad de
    año, aparecen dos), de la más reciente a la más antigua, y al final una
    fila `Total`. Las columnas `dif_*` siguen la convención de Understat
    (esperado − real): negativo = rindió por encima de lo esperado."""
    consulta = """
        SELECT t.anio_inicio AS temporada, jt.equipo, jt.partidos AS pj, jt.minutos,
               jt.goles AS g, jt.asistencias AS a, jt.disparos AS sh, jt.pases_clave AS kp,
               jt.xg, jt.xa
        FROM jugador_temporada jt
        JOIN temporada t ON t.id = jt.temporada_id
        WHERE jt.jugador_id = :jugador_id
        ORDER BY t.anio_inicio DESC, jt.minutos DESC
    """
    df = pd.read_sql_query(consulta, conexion, params={"jugador_id": jugador_id})
    if df.empty:
        return df

    if con_total:
        total = {"temporada": "Total", "equipo": ""}
        total.update(df[["pj", "minutos", "g", "a", "sh", "kp", "xg", "xa"]].sum().to_dict())
        df = pd.concat([df, pd.DataFrame([total])], ignore_index=True)

    df["sh90"] = _por_90(df["sh"], df["minutos"])
    df["kp90"] = _por_90(df["kp"], df["minutos"])
    df["xg90"] = _por_90(df["xg"], df["minutos"])
    df["xa90"] = _por_90(df["xa"], df["minutos"])
    df["dif_xg"] = df["xg"] - df["g"]
    df["dif_xa"] = df["xa"] - df["a"]
    return df


def _rol_en_disparos(
    conexion: sqlite3.Connection, jugador_id: int, columna_jugador: str, temporada: int | None
) -> pd.DataFrame:
    """Disparos en los que el jugador figura como `jugador_id` (ejecutante) o
    como `jugador_asistencia_id` (autor del pase)."""
    consulta = f"""
        SELECT d.x, d.y, d.situacion, d.tipo_disparo, d.es_gol, d.xg_understat
        FROM disparo d
        JOIN partido p ON p.id = d.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        WHERE d.{columna_jugador} = :jugador_id
          AND (:temporada IS NULL OR t.anio_inicio = :temporada)
    """
    df = pd.read_sql_query(consulta, conexion, params={"jugador_id": jugador_id, "temporada": temporada})
    df["zona"] = zona_de_tiro(df["x"], df["y"]) if not df.empty else pd.Series(dtype=object)
    return df


def _agrupar_por(df: pd.DataFrame, categoria: str, nombres: tuple[str, str, str]) -> pd.DataFrame:
    cantidad, goles, xg = nombres
    if df.empty:
        return pd.DataFrame(columns=[cantidad, goles, xg])
    agrupado = df.groupby(categoria).agg(
        **{cantidad: ("es_gol", "size"), goles: ("es_gol", "sum"), xg: ("xg_understat", "sum")}
    )
    return agrupado


def desglose_de_disparos(
    conexion: sqlite3.Connection,
    jugador_id: int,
    categoria: str,
    temporada: int | None = None,
    con_total: bool = True,
) -> pd.DataFrame:
    """Desglose de los disparos de un jugador por `situacion`, `tipo_disparo` o
    `zona` (pestañas "Situation", "Shot types" y "Shot zones" de Understat).

    - `sh`, `g`, `xg`: disparos que tiró, goles y su xG.
    - `kp`, `a`, `xa`: pases clave (pases que terminan en disparo de un
      compañero), asistencias (los que terminan en gol) y el xG de esos
      disparos. La categoría es la del disparo asistido.
    - `xg90`/`xa90` usan los minutos de la temporada elegida (o todos).
    - `dif_*` = esperado − real (convención de Understat).

    Devuelve un DataFrame vacío si el jugador no tiene disparos ni pases
    clave en esa selección.
    """
    if categoria not in CATEGORIAS_DESGLOSE:
        raise ValueError(f"categoria debe ser una de {CATEGORIAS_DESGLOSE}, no {categoria!r}")

    tiros = _agrupar_por(_rol_en_disparos(conexion, jugador_id, "jugador_id", temporada), categoria, ("sh", "g", "xg"))
    pases = _agrupar_por(
        _rol_en_disparos(conexion, jugador_id, "jugador_asistencia_id", temporada), categoria, ("kp", "a", "xa")
    )
    df = tiros.join(pases, how="outer").fillna(0)
    if df.empty:
        return df.reset_index().rename(columns={"index": "categoria"})

    df = df.reset_index().rename(columns={categoria: "categoria"})
    for columna in ("sh", "g", "kp", "a"):
        df[columna] = df[columna].astype(int)
    df = df.sort_values(["sh", "kp"], ascending=False).reset_index(drop=True)

    if con_total:
        total = {"categoria": "Total"}
        total.update(df[["sh", "g", "kp", "a", "xg", "xa"]].sum().to_dict())
        df = pd.concat([df, pd.DataFrame([total])], ignore_index=True)

    (minutos,) = conexion.execute(
        """
        SELECT COALESCE(SUM(jt.minutos), 0)
        FROM jugador_temporada jt JOIN temporada t ON t.id = jt.temporada_id
        WHERE jt.jugador_id = :jugador_id AND (:temporada IS NULL OR t.anio_inicio = :temporada)
        """,
        {"jugador_id": jugador_id, "temporada": temporada},
    ).fetchone()
    minutos_serie = pd.Series(minutos, index=df.index, dtype=float)

    df["dif_xg"] = df["xg"] - df["g"]
    df["dif_xa"] = df["xa"] - df["a"]
    df["xg90"] = _por_90(df["xg"], minutos_serie)
    df["xa90"] = _por_90(df["xa"], minutos_serie)
    # Sin disparos (o sin pases clave) el cociente queda en 0, como en Understat.
    df["xg_por_sh"] = (df["xg"] / df["sh"].where(df["sh"] > 0)).fillna(0.0)
    df["xa_por_kp"] = (df["xa"] / df["kp"].where(df["kp"] > 0)).fillna(0.0)
    return df
