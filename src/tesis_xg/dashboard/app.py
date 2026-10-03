"""Dashboard Streamlit (sección 8): 5 vistas, lectura directa desde
SQLite con caché de consultas. Se ejecuta con `python -m tesis_xg dashboard`.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from tesis_xg.almacenamiento import base
from tesis_xg.analisis import equipos, jugadores, ligas
from tesis_xg.analisis.formato import etiqueta_temporada
from tesis_xg.config import cargar_config

LARGO_CANCHA_M = 105.0
ANCHO_CANCHA_M = 68.0

st.set_page_config(page_title="tesis-xg", layout="wide")


@st.cache_resource
def _conexion() -> sqlite3.Connection:
    config = cargar_config()
    return base.crear(config.rutas.base_datos, check_same_thread=False)


@st.cache_data
def _ligas_disponibles(_conexion: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT codigo, nombre FROM liga ORDER BY nombre", _conexion)


@st.cache_data
def _temporadas_disponibles(_conexion: sqlite3.Connection, codigo_liga: str) -> list[int]:
    df = pd.read_sql_query(
        """
        SELECT DISTINCT t.anio_inicio FROM temporada t
        JOIN liga l ON l.id = t.liga_id
        WHERE l.codigo = :codigo_liga ORDER BY t.anio_inicio
        """,
        _conexion,
        params={"codigo_liga": codigo_liga},
    )
    return df["anio_inicio"].tolist()


@st.cache_data
def _equipos_de_liga(_conexion: sqlite3.Connection, codigo_liga: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT DISTINCT e.id, e.nombre
        FROM equipo e
        JOIN equipo_partido ep ON ep.equipo_id = e.id
        JOIN partido p ON p.id = ep.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        JOIN liga l ON l.id = t.liga_id
        WHERE l.codigo = :codigo_liga
        ORDER BY e.nombre
        """,
        _conexion,
        params={"codigo_liga": codigo_liga},
    )


@st.cache_data
def _partidos_de_temporada(_conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT p.id, p.fecha, eh.nombre AS local, ea.nombre AS visitante,
               p.goles_local, p.goles_visitante
        FROM partido p
        JOIN temporada t ON t.id = p.temporada_id
        JOIN liga l ON l.id = t.liga_id
        JOIN equipo eh ON eh.id = p.equipo_local_id
        JOIN equipo ea ON ea.id = p.equipo_visitante_id
        WHERE l.codigo = :codigo_liga AND t.anio_inicio = :temporada
        ORDER BY p.fecha
        """,
        _conexion,
        params={"codigo_liga": codigo_liga, "temporada": temporada},
    )


@st.cache_data
def _jugadores_de_temporada(_conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT DISTINCT jt.jugador_id, j.nombre
        FROM jugador_temporada jt
        JOIN jugador j ON j.id = jt.jugador_id
        JOIN temporada t ON t.id = jt.temporada_id
        JOIN liga l ON l.id = t.liga_id
        WHERE l.codigo = :codigo_liga AND t.anio_inicio = :temporada
        ORDER BY j.nombre
        """,
        _conexion,
        params={"codigo_liga": codigo_liga, "temporada": temporada},
    )


@st.cache_data
def _tabla_posiciones_vs_xpts(_conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> pd.DataFrame:
    return ligas.tabla_posiciones_vs_xpts(_conexion, codigo_liga, temporada)


@st.cache_data
def _evolucion_equipo(_conexion: sqlite3.Connection, equipo_id: int) -> pd.DataFrame:
    return equipos.evolucion_equipo_por_temporada(_conexion, equipo_id)


@st.cache_data
def _goles_vs_xg_jugadores(_conexion: sqlite3.Connection, temporada: int, minutos_minimos: int) -> pd.DataFrame:
    return jugadores.goles_vs_xg_por_jugador(_conexion, temporada, minutos_minimos)


@st.cache_data
def _evolucion_jugador(_conexion: sqlite3.Connection, jugador_id: int) -> pd.DataFrame:
    return jugadores.evolucion_jugador(_conexion, jugador_id)


@st.cache_data
def _disparos_de_jugador(_conexion: sqlite3.Connection, jugador_id: int, temporada: int | None) -> pd.DataFrame:
    return jugadores.disparos_de_jugador(_conexion, jugador_id, temporada)


@st.cache_data
def _disparos_de_partido(_conexion: sqlite3.Connection, partido_id: int) -> pd.DataFrame:
    return equipos.disparos_de_partido(_conexion, partido_id)


@st.cache_data
def _linea_tiempo_partido(_conexion: sqlite3.Connection, partido_id: int) -> pd.DataFrame:
    return equipos.linea_tiempo_xg_partido(_conexion, partido_id)


def _figura_cancha() -> go.Figure:
    """Cancha reglamentaria (105x68m), arco atacado a la derecha (x=105),
    tal como Understat normaliza las coordenadas de cada disparo."""
    fig = go.Figure()
    lineas = dict(line=dict(color="rgba(255,255,255,0.4)", width=1.5))

    fig.add_shape(type="rect", x0=0, y0=0, x1=LARGO_CANCHA_M, y1=ANCHO_CANCHA_M, **lineas)
    fig.add_shape(type="line", x0=LARGO_CANCHA_M / 2, y0=0, x1=LARGO_CANCHA_M / 2, y1=ANCHO_CANCHA_M, **lineas)
    fig.add_shape(
        type="circle",
        x0=LARGO_CANCHA_M / 2 - 9.15, y0=ANCHO_CANCHA_M / 2 - 9.15,
        x1=LARGO_CANCHA_M / 2 + 9.15, y1=ANCHO_CANCHA_M / 2 + 9.15,
        **lineas,
    )
    # Area grande y chica, solo del lado atacado (x=105)
    fig.add_shape(type="rect", x0=LARGO_CANCHA_M - 16.5, y0=13.84, x1=LARGO_CANCHA_M, y1=54.16, **lineas)
    fig.add_shape(type="rect", x0=LARGO_CANCHA_M - 5.5, y0=24.84, x1=LARGO_CANCHA_M, y1=43.16, **lineas)
    fig.add_shape(
        type="line",
        x0=LARGO_CANCHA_M, y0=ANCHO_CANCHA_M / 2 - 3.66,
        x1=LARGO_CANCHA_M, y1=ANCHO_CANCHA_M / 2 + 3.66,
        line=dict(color="white", width=4),
    )

    fig.update_xaxes(range=[-2, LARGO_CANCHA_M + 2], visible=False)
    fig.update_yaxes(range=[-2, ANCHO_CANCHA_M + 2], visible=False, scaleanchor="x", scaleratio=1)
    fig.update_layout(
        plot_bgcolor="#1e7a3c", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=30, b=0), height=450,
    )
    return fig


def _agregar_disparos_a_cancha(fig: go.Figure, disparos: pd.DataFrame, nombre: str, color: str) -> None:
    if disparos.empty:
        return
    disparos = disparos.copy()
    disparos["x_m"] = disparos["x"] * LARGO_CANCHA_M
    disparos["y_m"] = disparos["y"] * ANCHO_CANCHA_M
    disparos["tamano"] = 8 + disparos["xg_understat"] * 45

    no_gol = disparos[disparos["es_gol"] == 0]
    gol = disparos[disparos["es_gol"] == 1]

    fig.add_trace(
        go.Scatter(
            x=no_gol["x_m"], y=no_gol["y_m"], mode="markers", name=f"{nombre} — disparo",
            marker=dict(size=no_gol["tamano"], color=color, opacity=0.55, line=dict(width=1, color="white")),
            text=[f"xG {v:.2f}" for v in no_gol["xg_understat"]],
            hoverinfo="text",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=gol["x_m"], y=gol["y_m"], mode="markers", name=f"{nombre} — gol",
            marker=dict(size=gol["tamano"], color="gold", symbol="star", line=dict(width=1.5, color="black")),
            text=[f"GOL — xG {v:.2f}" for v in gol["xg_understat"]],
            hoverinfo="text",
        )
    )


COLUMNAS_TABLA_LIGA = {
    "posicion_real": "Pos", "equipo": "Equipo", "pj": "PJ", "pg": "PG", "pe": "PE", "pp": "PP",
    "g": "G", "ga": "GA", "dg": "DG", "puntos": "Pts",
    "xg": "xG", "dif_xg": "Δ xG", "xga": "xGA", "dif_xga": "Δ xGA",
    "xpts": "xPTS", "dif_xpts": "Δ xPTS",
    "diferencia_posicion": "Dif. pos",
}


def _color_diferencia(valor: float, positivo_es_bueno: bool) -> str:
    """Verde si el equipo rindió por encima de lo esperado, rojo si por debajo."""
    if valor == 0:
        return ""
    bueno = (valor > 0) == positivo_es_bueno
    return "color: #2ecc71; font-weight: 600" if bueno else "color: #e74c3c; font-weight: 600"


def _tabla_liga_con_estilo(df: pd.DataFrame):
    """Las columnas Δ siguen la convención de Understat (esperado − real):
    en xG y xPTS un valor negativo es sobreperformance; en xGA, positivo."""
    # posicion_xpts se calcula igual (la usa el gráfico de abajo) pero no se
    # muestra: alcanza con ordenar la tabla por la columna xPTS.
    tabla = df.drop(columns=["posicion_xpts"]).rename(columns=COLUMNAS_TABLA_LIGA)
    return (
        tabla.style
        .map(lambda v: _color_diferencia(v, positivo_es_bueno=False), subset=["Δ xG", "Δ xPTS"])
        .map(lambda v: _color_diferencia(v, positivo_es_bueno=True), subset=["Δ xGA"])
        .format({
            "xG": "{:.2f}", "xGA": "{:.2f}", "xPTS": "{:.2f}",
            "Δ xG": "{:+.2f}", "Δ xGA": "{:+.2f}", "Δ xPTS": "{:+.2f}",
            "DG": "{:+d}",
        })
    )


def _vista_liga(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> None:
    st.header(f"Tabla de posiciones real vs. xPTS — {codigo_liga} {etiqueta_temporada(temporada)}")
    df = _tabla_posiciones_vs_xpts(conexion, codigo_liga, temporada)
    st.dataframe(
        _tabla_liga_con_estilo(df), use_container_width=True, hide_index=True,
        height=(len(df) + 1) * 35 + 3,
        column_config={"Equipo": st.column_config.TextColumn("Equipo", width=200)},
    )
    st.caption(
        "Δ = esperado − real (convención de Understat). Verde: rindió por encima de lo esperado "
        "(más goles que xG, menos goles recibidos que xGA, más puntos que xPTS); rojo: por debajo. "
        "La tabla se calcula con los resultados de los partidos: no incluye quitas administrativas "
        "de puntos."
    )

    fig = px.bar(
        df.sort_values("diferencia_posicion"), x="equipo", y="diferencia_posicion",
        title="Diferencia de posición (real − xPTS): negativo = terminó mejor que lo esperado",
        color="diferencia_posicion", color_continuous_scale="RdBu_r",
    )
    st.plotly_chart(fig, use_container_width=True)


def _vista_equipo(conexion: sqlite3.Connection, codigo_liga: str) -> None:
    equipos_df = _equipos_de_liga(conexion, codigo_liga)
    nombre = st.selectbox("Equipo", equipos_df["nombre"])
    equipo_id = int(equipos_df.set_index("nombre").loc[nombre, "id"])

    st.header(f"Evolución — {nombre}")
    df = _evolucion_equipo(conexion, equipo_id)
    if df.empty:
        st.info("Sin datos para este equipo.")
        return
    df = df.assign(temporada=df["temporada"].map(etiqueta_temporada))

    fig_xg = px.line(df, x="temporada", y=["xg", "xga"], markers=True, title="xG / xGA por temporada")
    st.plotly_chart(fig_xg, use_container_width=True)

    fig_ppda = px.line(df, x="temporada", y="ppda_coef", markers=True, title="ppda por temporada")
    st.plotly_chart(fig_ppda, use_container_width=True)

    st.dataframe(df, use_container_width=True, hide_index=True)


def _vista_jugador(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> None:
    jugadores_df = _jugadores_de_temporada(conexion, codigo_liga, temporada)
    if jugadores_df.empty:
        st.info("Sin jugadores para esta liga/temporada.")
        return
    nombre = st.selectbox("Jugador", jugadores_df["nombre"])
    jugador_id = int(jugadores_df.set_index("nombre").loc[nombre, "jugador_id"])

    st.header(f"Goles contra xG por temporada — {nombre}")
    evolucion = _evolucion_jugador(conexion, jugador_id)
    evolucion = evolucion.assign(temporada=evolucion["temporada"].map(etiqueta_temporada))
    fig = px.bar(
        evolucion, x="temporada", y=["goles", "xg_understat"], barmode="group",
        title="Goles vs. xG por temporada",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader(f"Mapa de disparos — {etiqueta_temporada(temporada)}")
    disparos = _disparos_de_jugador(conexion, jugador_id, temporada)
    fig_cancha = _figura_cancha()
    _agregar_disparos_a_cancha(fig_cancha, disparos, nombre, "dodgerblue")
    st.plotly_chart(fig_cancha, use_container_width=True)


def _selector_partido(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> int | None:
    partidos = _partidos_de_temporada(conexion, codigo_liga, temporada)
    if partidos.empty:
        st.info("Sin partidos para esta liga/temporada.")
        return None
    partidos = partidos.copy()
    partidos["etiqueta"] = (
        partidos["fecha"].str.slice(0, 10) + ": " + partidos["local"] + " " +
        partidos["goles_local"].astype(str) + "-" + partidos["goles_visitante"].astype(str) +
        " " + partidos["visitante"]
    )
    etiqueta = st.selectbox("Partido", partidos["etiqueta"])
    return int(partidos.set_index("etiqueta").loc[etiqueta, "id"])


def _vista_partido(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> None:
    partido_id = _selector_partido(conexion, codigo_liga, temporada)
    if partido_id is None:
        return

    st.header("Mapa de disparos")
    disparos = _disparos_de_partido(conexion, partido_id)
    equipos_partido = disparos[["equipo_id", "equipo"]].drop_duplicates().to_records(index=False)
    colores = ["crimson", "royalblue"]

    fig = _figura_cancha()
    for (equipo_id, nombre_equipo), color in zip(equipos_partido, colores):
        _agregar_disparos_a_cancha(fig, disparos[disparos["equipo_id"] == equipo_id], nombre_equipo, color)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(disparos, use_container_width=True, hide_index=True)


def _vista_linea_tiempo(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> None:
    partido_id = _selector_partido(conexion, codigo_liga, temporada)
    if partido_id is None:
        return

    st.header("xG acumulado a lo largo del partido")
    linea = _linea_tiempo_partido(conexion, partido_id)
    fig = px.line(linea, x="minuto", y="xg_acumulado", color="equipo", markers=True, line_shape="hv")
    fig.update_xaxes(range=[0, 95])
    st.plotly_chart(fig, use_container_width=True)


def main() -> None:
    conexion = _conexion()

    st.sidebar.title("tesis-xg")
    ligas_df = _ligas_disponibles(conexion)
    codigo_liga = st.sidebar.selectbox(
        "Liga", ligas_df["codigo"],
        format_func=lambda c: ligas_df.set_index("codigo").loc[c, "nombre"],
    )
    temporadas = _temporadas_disponibles(conexion, codigo_liga)
    temporada = st.sidebar.selectbox(
        "Temporada", temporadas, index=len(temporadas) - 1, format_func=etiqueta_temporada
    )

    vista = st.sidebar.radio("Vista", ["Liga", "Equipo", "Jugador", "Partido", "Línea de tiempo"])

    if vista == "Liga":
        _vista_liga(conexion, codigo_liga, temporada)
    elif vista == "Equipo":
        _vista_equipo(conexion, codigo_liga)
    elif vista == "Jugador":
        _vista_jugador(conexion, codigo_liga, temporada)
    elif vista == "Partido":
        _vista_partido(conexion, codigo_liga, temporada)
    elif vista == "Línea de tiempo":
        _vista_linea_tiempo(conexion, codigo_liga, temporada)


main()
