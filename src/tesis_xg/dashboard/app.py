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
def _todas_las_temporadas(_conexion: sqlite3.Connection) -> list[int]:
    df = pd.read_sql_query("SELECT DISTINCT anio_inicio FROM temporada ORDER BY anio_inicio", _conexion)
    return df["anio_inicio"].tolist()


@st.cache_data
def _buscar_jugadores(
    _conexion: sqlite3.Connection, codigo_liga: str | None, temporada: int | None
) -> pd.DataFrame:
    return jugadores.buscar_jugadores(_conexion, codigo_liga, temporada)


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


COLUMNAS_EVOLUCION_EQUIPO = {"temporada": "Temporada", "xg": "xG", "xga": "xGA", "ppda_coef": "ppda"}

COLUMNAS_DISPAROS = {
    "id": "ID", "equipo_id": "ID equipo", "equipo": "Equipo",
    "jugador_id": "ID jugador", "jugador": "Jugador", "minuto": "Min",
    "x": "X", "y": "Y", "resultado": "Resultado", "es_gol": "Gol",
    "xg_understat": "xG Understat", "xg_propio": "xG propio",
}


def _mostrar_tabla(df: pd.DataFrame, etiquetas: dict[str, str]) -> None:
    """Tabla con etiquetas legibles y las columnas decimales a 2 decimales."""
    formato = {
        etiquetas.get(columna, columna): st.column_config.NumberColumn(format="%.2f")
        for columna in df.columns
        if pd.api.types.is_float_dtype(df[columna])
    }
    st.dataframe(
        df.rename(columns=etiquetas), use_container_width=True, hide_index=True, column_config=formato
    )


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
        labels={"equipo": "Equipo", "diferencia_posicion": "Diferencia de posición"},
    )
    fig.update_layout(coloraxis_colorbar_title_text="Dif. pos")
    st.plotly_chart(fig, use_container_width=True)


def _figura_evolucion_equipo(df: pd.DataFrame) -> go.Figure:
    """xG/xGA y ppda en dos paneles apilados que comparten un único eje de
    temporadas: mismo ancho exacto y líneas verticales continuas para leer un
    año de arriba a abajo, y cada métrica en su propia escala (mezclarlas en un
    solo eje Y daría cruces sin significado). El tooltip es por panel: Plotly
    no junta series de paneles distintos en un mismo cuadro."""
    fig = go.Figure()
    series = [
        ("xg", "xG", "#74c0fc", "y"),
        ("xga", "xGA", "#ff8787", "y"),
        ("ppda_coef", "ppda", "#ffd43b", "y2"),
    ]
    for columna, nombre, color, eje_y in series:
        fig.add_trace(
            go.Scatter(
                x=df["temporada"], y=df[columna], name=nombre, mode="lines+markers",
                line=dict(color=color), yaxis=eje_y, hovertemplate="%{y:.2f}",
            )
        )

    fig.update_layout(
        height=650, hovermode="x unified",
        xaxis=dict(
            anchor="y2", title="Temporada", showgrid=True,
            showspikes=True, spikemode="across", spikethickness=1,
        ),
        yaxis=dict(domain=[0.58, 1.0]),
        yaxis2=dict(domain=[0.0, 0.42], anchor="x"),
        legend=dict(orientation="h", yanchor="bottom", y=1.1, x=0),
        margin=dict(t=100),
    )
    for texto, y in (("xG y xGA (suma de la temporada)", 1.0), ("ppda (promedio por partido)", 0.42)):
        fig.add_annotation(
            text=f"<b>{texto}</b>", xref="paper", yref="paper", x=0, y=y,
            xanchor="left", yanchor="bottom", showarrow=False,
        )
    return fig


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

    st.plotly_chart(_figura_evolucion_equipo(df), use_container_width=True)
    st.caption(
        "xG y xGA son la suma de la temporada; ppda es el promedio por partido (pases permitidos "
        "por acción defensiva: un valor más bajo implica una presión más intensa). Hacé clic en la "
        "leyenda para ocultar o mostrar cada serie."
    )

    _mostrar_tabla(df, COLUMNAS_EVOLUCION_EQUIPO)


def _etiqueta_jugador(fila) -> str:
    """Nombre + último equipo + años de carrera: distingue a los homónimos y
    permite buscar también escribiendo el nombre de un equipo."""
    carrera = f"{etiqueta_temporada(fila.desde)}–{etiqueta_temporada(fila.hasta)}"
    return f"{fila.nombre} — {fila.equipo} ({carrera})"


def _vista_jugador(conexion: sqlite3.Connection) -> None:
    # Los filtros solo acotan a quién se puede buscar; lo que se muestra del
    # jugador (historial y mapa) no depende de ellos.
    with st.expander("Filtrar la búsqueda por liga y temporada (opcional)"):
        columna_liga, columna_temporada = st.columns(2)
        nombres_liga = _ligas_disponibles(conexion).set_index("codigo")["nombre"].to_dict()
        filtro_liga = columna_liga.selectbox(
            "Liga", [None, *nombres_liga],
            format_func=lambda c: "Todas" if c is None else nombres_liga[c],
        )
        filtro_temporada = columna_temporada.selectbox(
            "Temporada", [None, *_todas_las_temporadas(conexion)],
            format_func=lambda t: "Todas" if t is None else etiqueta_temporada(t),
        )

    candidatos = _buscar_jugadores(conexion, filtro_liga, filtro_temporada)
    if candidatos.empty:
        st.info("Ningún jugador coincide con esos filtros.")
        return

    etiquetas = {int(fila.jugador_id): _etiqueta_jugador(fila) for fila in candidatos.itertuples()}
    ids = list(etiquetas)
    # Streamlit descarta el valor de un widget que no se dibuja en una corrida
    # (p. ej. al pasar por otra vista): el jugador elegido se recuerda aparte.
    guardado = st.session_state.get("jugador_elegido")
    jugador_id = st.selectbox(
        "Jugador", ids, index=ids.index(guardado) if guardado in ids else None,
        format_func=etiquetas.get, placeholder="Escribí el nombre del jugador (o de su equipo)",
    )
    st.session_state["jugador_elegido"] = jugador_id
    if jugador_id is None:
        st.info("Buscá un jugador por nombre para ver su historial.")
        return
    nombre = candidatos.set_index("jugador_id").loc[jugador_id, "nombre"]

    st.header(f"Goles contra xG por temporada — {nombre}")
    evolucion = _evolucion_jugador(conexion, jugador_id)
    temporadas_jugadas = evolucion["temporada"].tolist()
    evolucion = evolucion.assign(temporada=evolucion["temporada"].map(etiqueta_temporada))
    evolucion = evolucion.rename(columns={"goles": "Goles", "xg_understat": "xG"})
    fig = px.bar(
        evolucion, x="temporada", y=["Goles", "xG"], barmode="group",
        title="Goles vs. xG por temporada (historial completo)",
        labels={"temporada": "Temporada", "value": "Goles / xG", "variable": "Serie"},
    )
    fig.update_layout(yaxis_hoverformat=".2f", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Mapa de disparos")
    temporada_mapa = st.selectbox(
        "Disparos de", [None, *temporadas_jugadas],
        format_func=lambda t: "Todas las temporadas" if t is None else etiqueta_temporada(t),
    )
    disparos = _disparos_de_jugador(conexion, jugador_id, temporada_mapa)
    st.caption(
        f"{len(disparos)} disparos · {int(disparos['es_gol'].sum())} goles · "
        f"xG {disparos['xg_understat'].sum():.2f}"
    )
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
    tabla = disparos.assign(es_gol=disparos["es_gol"].map({1: "Sí", 0: "No"}))
    _mostrar_tabla(tabla, COLUMNAS_DISPAROS)


def _vista_linea_tiempo(conexion: sqlite3.Connection, codigo_liga: str, temporada: int) -> None:
    partido_id = _selector_partido(conexion, codigo_liga, temporada)
    if partido_id is None:
        return

    st.header("xG acumulado a lo largo del partido")
    linea = _linea_tiempo_partido(conexion, partido_id)
    fig = px.line(
        linea, x="minuto", y="xg_acumulado", color="equipo", markers=True, line_shape="hv",
        labels={"minuto": "Minuto", "xg_acumulado": "xG acumulado", "equipo": "Equipo"},
    )
    fig.update_xaxes(range=[0, 95])
    fig.update_layout(yaxis_hoverformat=".2f", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)


VISTAS = ["Liga", "Equipo", "Jugador", "Partido", "Línea de tiempo"]
# Filtros de la barra lateral que usa cada vista. Equipo es un histórico de todas las
# temporadas, y Jugador tiene su propio buscador: ninguno de los dos filtra por temporada.
VISTAS_CON_LIGA = {"Liga", "Equipo", "Partido", "Línea de tiempo"}
VISTAS_CON_TEMPORADA = {"Liga", "Partido", "Línea de tiempo"}


def main() -> None:
    conexion = _conexion()

    st.sidebar.title("tesis-xg")
    # El contenedor se crea antes del radio para que los filtros queden
    # arriba, pero se completa después: los filtros dependen de la vista.
    filtros = st.sidebar.container()
    vista = st.sidebar.radio("Vista", VISTAS)

    codigo_liga = temporada = None
    with filtros:
        # Streamlit descarta el valor de un widget que no se dibuja en una
        # corrida (p. ej. al pasar por Jugador): se recuerda aparte.
        if vista in VISTAS_CON_LIGA:
            ligas_df = _ligas_disponibles(conexion)
            codigos = ligas_df["codigo"].tolist()
            guardada = st.session_state.get("liga_elegida")
            codigo_liga = st.selectbox(
                "Liga", codigos, index=codigos.index(guardada) if guardada in codigos else 0,
                format_func=lambda c: ligas_df.set_index("codigo").loc[c, "nombre"],
            )
            st.session_state["liga_elegida"] = codigo_liga

        if vista in VISTAS_CON_TEMPORADA:
            temporadas = _temporadas_disponibles(conexion, codigo_liga)
            guardada = st.session_state.get("temporada_elegida")
            indice = temporadas.index(guardada) if guardada in temporadas else len(temporadas) - 1
            temporada = st.selectbox(
                "Temporada", temporadas, index=indice, format_func=etiqueta_temporada
            )
            st.session_state["temporada_elegida"] = temporada

    if vista == "Liga":
        _vista_liga(conexion, codigo_liga, temporada)
    elif vista == "Equipo":
        _vista_equipo(conexion, codigo_liga)
    elif vista == "Jugador":
        _vista_jugador(conexion)
    elif vista == "Partido":
        _vista_partido(conexion, codigo_liga, temporada)
    elif vista == "Línea de tiempo":
        _vista_linea_tiempo(conexion, codigo_liga, temporada)


main()
