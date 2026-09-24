from pathlib import Path

import pytest

from tesis_xg.almacenamiento import base
from tesis_xg.analisis import equipos, jugadores, ligas

# Un "partido" por equipo alcanza para controlar los agregados de
# equipo_partido sin tener que armar una temporada completa realista.
EQUIPOS = {
    # id: (nombre, puntos, xg, xga, xpts, ppda_coef, resultado)
    1: ("A", 30, 40, 20, 25, 8.0, "w"),
    2: ("B", 25, 22, 25, 27, 12.0, "w"),
    3: ("C", 20, 18, 18, 15, 9.0, "d"),
    4: ("D", 15, 25, 30, 20, 15.0, "l"),
    5: ("E", 10, 10, 10, 8, 7.0, "l"),
    6: ("F", 5, 5, 35, 6, 20.0, "l"),
}


def _poblar(conexion) -> None:
    conexion.executescript(
        """
        INSERT INTO liga (codigo, nombre, pais) VALUES ('EPL', 'Premier League', 'Inglaterra');
        INSERT INTO temporada (liga_id, anio_inicio) VALUES (1, 2020);
        """
    )
    for equipo_id, (nombre, *_resto) in EQUIPOS.items():
        conexion.execute("INSERT INTO equipo (id, nombre) VALUES (?, ?)", (equipo_id, nombre))

    conexion.execute("INSERT INTO jugador (id, nombre) VALUES (100, 'Jugador Uno')")

    # 3 partidos (A-B, C-D, E-F): un equipo_partido por equipo, con los
    # totales elegidos a mano para la temporada.
    pares = [(1, 2), (3, 4), (5, 6)]
    for partido_id, (local_id, visitante_id) in enumerate(pares, start=1):
        conexion.execute(
            """
            INSERT INTO partido
                (id, temporada_id, fecha, equipo_local_id, equipo_visitante_id, goles_local, goles_visitante)
            VALUES (?, 1, '2020-09-01T15:00:00', ?, ?, 1, 0)
            """,
            (partido_id, local_id, visitante_id),
        )
        for condicion, equipo_id in (("h", local_id), ("a", visitante_id)):
            _, puntos, xg, xga, xpts, ppda_coef, resultado = EQUIPOS[equipo_id]
            conexion.execute(
                """
                INSERT INTO equipo_partido
                    (partido_id, equipo_id, condicion, xg, xga, xpts, puntos, ppda_coef, resultado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (partido_id, equipo_id, condicion, xg, xga, xpts, puntos, ppda_coef, resultado),
            )

    # Disparos de un partido puntual, para el mapa de disparos / linea de tiempo
    conexion.executescript(
        """
        INSERT INTO disparo
            (id, partido_id, equipo_id, jugador_id, minuto, x, y,
             resultado, situacion, tipo_disparo, es_gol, xg_understat, xg_propio)
        VALUES
            (1, 1, 1, 100, 10, 0.85, 0.5, 'MissedShots', 'OpenPlay', 'RightFoot', 0, 0.10, 0.12),
            (2, 1, 1, 100, 40, 0.90, 0.5, 'Goal',        'OpenPlay', 'RightFoot', 1, 0.30, 0.28),
            (3, 1, 2, 100, 25, 0.88, 0.4, 'SavedShot',   'OpenPlay', 'LeftFoot',  0, 0.15, 0.14);
        """
    )
    conexion.commit()


def _poblar_jugadores_temporada(conexion) -> None:
    conexion.execute("INSERT INTO jugador (id, nombre) VALUES (200, 'Titular'), (300, 'Suplente')")
    conexion.executemany(
        """
        INSERT INTO jugador_temporada
            (jugador_id, temporada_id, equipo, posicion, partidos, minutos, goles, goles_np,
             asistencias, xg, xg_np, xa, disparos, pases_clave)
        VALUES (?, 1, 'A', 'F', 20, ?, ?, ?, 2, ?, ?, 1.0, 50, 10)
        """,
        [
            (200, 1800, 15, 15, 10.0, 10.0),  # >= minutos_minimos
            (300, 300, 2, 2, 3.0, 3.0),       # por debajo del minimo por defecto (900)
        ],
    )
    conexion.commit()


@pytest.fixture()
def conexion(tmp_path: Path):
    conexion = base.crear(tmp_path / "tesis.db")
    _poblar(conexion)
    yield conexion
    conexion.close()


def test_evolucion_xg_top5_excluye_el_ultimo_y_ordena_por_puntos(conexion) -> None:
    df = ligas.evolucion_xg_top5(conexion, "EPL")
    assert list(df["equipo"]) == ["A", "B", "C", "D", "E"]  # F (5 puntos) queda afuera
    assert list(df["posicion"]) == [1, 2, 3, 4, 5]
    assert df[df["equipo"] == "A"]["xg"].iloc[0] == pytest.approx(40)


def test_tabla_posiciones_vs_xpts(conexion) -> None:
    df = ligas.tabla_posiciones_vs_xpts(conexion, "EPL", 2020)

    fila_a = df[df["equipo"] == "A"].iloc[0]
    assert fila_a["posicion_real"] == 1
    assert fila_a["posicion_xpts"] == 2  # B tiene mas xpts (27) que A (25)
    assert fila_a["diferencia_posicion"] == -1

    fila_b = df[df["equipo"] == "B"].iloc[0]
    assert fila_b["posicion_real"] == 2
    assert fila_b["posicion_xpts"] == 1
    assert fila_b["diferencia_posicion"] == 1

    fila_e = df[df["equipo"] == "E"].iloc[0]
    assert fila_e["diferencia_posicion"] == 0


def test_porcentaje_victorias_segun_xg_y_ppda(conexion) -> None:
    df = equipos.porcentaje_victorias_segun_xg_y_ppda(conexion, codigo_liga="EPL")

    def valor(variable, grupo):
        fila = df[(df["variable"] == variable) & (df["grupo"] == grupo)].iloc[0]
        return fila["porcentaje_victorias"], fila["n"]

    pct, n = valor("xG", "por encima de la media")  # A, B, D (xg > 20)
    assert n == 3
    assert pct == pytest.approx(2 / 3)  # A y B ganan, D pierde

    pct, n = valor("xG", "por debajo de la media")  # C, E, F
    assert n == 3
    assert pct == pytest.approx(0.0)

    pct, n = valor("ppda", "por encima de la media")  # B, D, F (> 11.833)
    assert n == 3
    assert pct == pytest.approx(1 / 3)  # solo B gana


def test_disparos_y_linea_tiempo_de_partido(conexion) -> None:
    disparos = equipos.disparos_de_partido(conexion, partido_id=1)
    assert len(disparos) == 3
    assert list(disparos["minuto"]) == [10, 25, 40]  # ordenado por minuto

    linea = equipos.linea_tiempo_xg_partido(conexion, partido_id=1)
    equipo_1 = linea[linea["equipo_id"] == 1].sort_values("minuto")
    # equipo 1 tira en el minuto 10 (0.10) y el 40 (0.30): acumulado 0.10, luego 0.40
    assert list(equipo_1["xg_acumulado"]) == pytest.approx([0.10, 0.40])


def test_evolucion_equipo_por_temporada(conexion) -> None:
    df = equipos.evolucion_equipo_por_temporada(conexion, equipo_id=1)  # A
    assert len(df) == 1
    fila = df.iloc[0]
    assert fila["temporada"] == 2020
    assert fila["xg"] == pytest.approx(40)
    assert fila["xga"] == pytest.approx(20)
    assert fila["ppda_coef"] == pytest.approx(8.0)


def test_goles_vs_xg_por_jugador_respeta_minutos_minimos(conexion) -> None:
    _poblar_jugadores_temporada(conexion)

    df = jugadores.goles_vs_xg_por_jugador(conexion, temporada=2020, minutos_minimos=900)

    assert list(df["jugador_id"]) == [200]  # el suplente (300 min) queda afuera
    fila = df.iloc[0]
    assert fila["goles"] == 15
    assert fila["xg_understat"] == pytest.approx(10.0)
    assert fila["goles_menos_xg"] == pytest.approx(5.0)


def test_evolucion_jugador(conexion) -> None:
    _poblar_jugadores_temporada(conexion)

    df = jugadores.evolucion_jugador(conexion, jugador_id=200)
    assert len(df) == 1
    fila = df.iloc[0]
    assert fila["temporada"] == 2020
    assert fila["goles"] == 15
    assert fila["xg_understat"] == pytest.approx(10.0)


def test_disparos_de_jugador(conexion) -> None:
    disparos = jugadores.disparos_de_jugador(conexion, jugador_id=100)
    assert len(disparos) == 3

    disparos_2020 = jugadores.disparos_de_jugador(conexion, jugador_id=100, temporada=2020)
    assert len(disparos_2020) == 3

    disparos_otra_temporada = jugadores.disparos_de_jugador(conexion, jugador_id=100, temporada=1999)
    assert len(disparos_otra_temporada) == 0
