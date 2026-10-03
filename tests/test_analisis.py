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
                    (partido_id, equipo_id, condicion, xg, xga, xpts, puntos, ppda_coef, resultado,
                     goles, goles_recibidos)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
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


def _tabla_con_empate(tmp_path: Path, codigo_liga: str, partidos: list[tuple[int, int, int, int]]):
    """Arma una temporada chica con los partidos dados (local, visitante,
    goles_local, goles_visitante) y devuelve la tabla calculada."""
    conexion = base.crear(tmp_path / f"{codigo_liga}.db")
    conexion.executescript(
        f"""
        INSERT INTO liga (codigo, nombre, pais) VALUES ('{codigo_liga}', 'Liga', 'Pais');
        INSERT INTO temporada (liga_id, anio_inicio) VALUES (1, 2020);
        INSERT INTO equipo (id, nombre) VALUES (1, 'A'), (2, 'B'), (3, 'C');
        """
    )
    for partido_id, (local, visitante, gl, gv) in enumerate(partidos, start=1):
        conexion.execute(
            """
            INSERT INTO partido (id, temporada_id, fecha, equipo_local_id, equipo_visitante_id,
                                 goles_local, goles_visitante)
            VALUES (?, 1, '2020-09-01T15:00:00', ?, ?, ?, ?)
            """,
            (partido_id, local, visitante, gl, gv),
        )
        for condicion, equipo_id, goles, recibidos in (("h", local, gl, gv), ("a", visitante, gv, gl)):
            puntos = 3 if goles > recibidos else 1 if goles == recibidos else 0
            resultado = "w" if goles > recibidos else "d" if goles == recibidos else "l"
            conexion.execute(
                """
                INSERT INTO equipo_partido
                    (partido_id, equipo_id, condicion, xg, xga, xpts, puntos, resultado,
                     goles, goles_recibidos)
                VALUES (?, ?, ?, 1.0, 1.0, 1.0, ?, ?, ?, ?)
                """,
                (partido_id, equipo_id, condicion, puntos, resultado, goles, recibidos),
            )
    conexion.commit()
    try:
        return ligas.tabla_posiciones_vs_xpts(conexion, codigo_liga, 2020)
    finally:
        conexion.close()


def test_empate_en_puntos_se_resuelve_por_diferencia_de_gol_y_nunca_repite_posicion(tmp_path: Path) -> None:
    # A (1-0 y empate contra C) y B (4-0 y empate contra C) suman 4 puntos cada uno;
    # B tiene mejor diferencia de gol (+4 vs. +1).
    partidos = [(1, 3, 1, 0), (2, 3, 4, 0), (3, 1, 0, 0), (3, 2, 0, 0)]
    df = _tabla_con_empate(tmp_path, "EPL", partidos)
    puntos = dict(zip(df["equipo"], df["puntos"]))
    assert puntos["A"] == puntos["B"]  # hay empate en puntos
    assert sorted(df["posicion_real"]) == [1, 2, 3]  # posiciones únicas
    posiciones = dict(zip(df["equipo"], df["posicion_real"]))
    assert posiciones["B"] < posiciones["A"]  # B tiene mejor diferencia de gol (+4 vs +1)


def test_desempate_por_enfrentamiento_directo_en_la_liga_y_serie_a(tmp_path: Path) -> None:
    # A y B empatan en puntos; B tiene mejor diferencia de gol general,
    # pero A le ganó el cruce directo: en La Liga manda el cruce directo.
    partidos = [
        (1, 2, 1, 0),  # A le gana a B
        (2, 1, 0, 0),  # empatan la vuelta -> mini-tabla: A 4 pts, B 1
        (2, 3, 6, 0),  # B golea a C (B: gran diferencia de gol)
        (3, 1, 0, 0),
        (3, 2, 0, 0),
    ]
    en_epl = _tabla_con_empate(tmp_path, "EPL", partidos)
    en_la_liga = _tabla_con_empate(tmp_path, "La_liga", partidos)

    puntos = dict(zip(en_la_liga["equipo"], en_la_liga["puntos"]))
    assert puntos["A"] == puntos["B"]

    pos_epl = dict(zip(en_epl["equipo"], en_epl["posicion_real"]))
    pos_liga = dict(zip(en_la_liga["equipo"], en_la_liga["posicion_real"]))
    assert pos_epl["B"] < pos_epl["A"]      # EPL: diferencia de gol general
    assert pos_liga["A"] < pos_liga["B"]    # La Liga: enfrentamiento directo


def test_buscar_jugadores_el_filtro_acota_quien_aparece_pero_no_su_trayectoria(conexion) -> None:
    _poblar_jugadores_temporada(conexion)
    # El jugador 200 sigue una temporada más (2021) en otro equipo.
    conexion.execute("INSERT INTO temporada (liga_id, anio_inicio) VALUES (1, 2021)")
    conexion.execute(
        """
        INSERT INTO jugador_temporada
            (jugador_id, temporada_id, equipo, posicion, partidos, minutos, goles, goles_np,
             asistencias, xg, xg_np, xa, disparos, pases_clave)
        VALUES (200, 2, 'B', 'F', 10, 900, 5, 5, 1, 4.0, 4.0, 0.5, 20, 5)
        """
    )
    conexion.commit()

    todos = jugadores.buscar_jugadores(conexion)
    titular = todos[todos["jugador_id"] == 200].iloc[0]
    assert (titular["desde"], titular["hasta"], titular["equipo"]) == (2020, 2021, "B")  # equipo más reciente

    # Con filtro de temporada 2020 aparecen 200 y 300 ...
    en_2020 = jugadores.buscar_jugadores(conexion, temporada=2020)
    assert set(en_2020["jugador_id"]) == {200, 300}
    # ... pero la trayectoria de 200 sigue siendo la completa (no se recorta a 2020).
    assert en_2020[en_2020["jugador_id"] == 200].iloc[0]["hasta"] == 2021

    # Solo 200 jugó en 2021; y una liga o temporada inexistente no devuelve a nadie.
    assert set(jugadores.buscar_jugadores(conexion, temporada=2021)["jugador_id"]) == {200}
    assert set(jugadores.buscar_jugadores(conexion, codigo_liga="EPL")["jugador_id"]) == {200, 300}
    assert jugadores.buscar_jugadores(conexion, codigo_liga="XXX").empty
