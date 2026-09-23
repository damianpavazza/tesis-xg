import math

import pytest

from tesis_xg.almacenamiento import base
from tesis_xg.modelo.features import calcular_distancia_angulo, completar_variables_derivadas


def test_disparo_centrado_sobre_la_linea_de_gol() -> None:
    """x=1, y=0.5: parado justo en el medio de la línea de gol.
    A mano: dx=0, dy=0 -> distancia=0; el arco se ve en su ángulo máximo (pi)."""
    distancia, angulo = calcular_distancia_angulo(x=1.0, y=0.5)
    assert distancia == pytest.approx(0.0)
    assert angulo == pytest.approx(math.pi)


def test_disparo_centrado_a_21m() -> None:
    """x=0.8, y=0.5 -> x_m=84, dx=105-84=21; y_m=34, dy=0.
    A mano: distancia=21m.
    Verificación cruzada del ángulo con la fórmula geométrica equivalente
    (ecuación de la tangente del ángulo subtendido, sin pasar por atan2):
    angulo = 2*atan((ancho_arco/2) / dx)."""
    distancia, angulo = calcular_distancia_angulo(x=0.8, y=0.5)
    assert distancia == pytest.approx(21.0)
    angulo_esperado = 2 * math.atan((7.32 / 2) / 21.0)
    assert angulo == pytest.approx(angulo_esperado)


def test_disparo_descentrado() -> None:
    """x=0.7, y=0.2 -> x_m=73.5, dx=105-73.5=31.5; y_m=13.6, dy=|34-13.6|=20.4.
    A mano: distancia = sqrt(31.5^2 + 20.4^2) = sqrt(992.25 + 416.16) = sqrt(1408.41).
    El ángulo se recalcula acá de forma independiente (reescribiendo la
    fórmula de la sección 6.1 con otros nombres) para no depender de que
    el propio módulo se esté auto-confirmando."""
    distancia, angulo = calcular_distancia_angulo(x=0.7, y=0.2)

    dx_esperado = 105 - 0.7 * 105
    dy_esperado = abs(34 - 0.2 * 68)
    assert dx_esperado == pytest.approx(31.5)
    assert dy_esperado == pytest.approx(20.4)

    distancia_esperada = math.sqrt(dx_esperado**2 + dy_esperado**2)
    assert distancia == pytest.approx(distancia_esperada)
    assert distancia == pytest.approx(math.sqrt(1408.41))

    ancho = 7.32
    angulo_esperado = math.atan2(
        ancho * dx_esperado, dx_esperado**2 + dy_esperado**2 - (ancho / 2) ** 2
    )
    if angulo_esperado < 0:
        angulo_esperado += math.pi
    assert angulo == pytest.approx(angulo_esperado)


def test_completar_variables_derivadas_persiste_en_la_base(tmp_path) -> None:
    conexion = base.crear(tmp_path / "tesis.db")
    try:
        conexion.executescript(
            """
            INSERT INTO liga (codigo, nombre, pais) VALUES ('EPL', 'Premier League', 'Inglaterra');
            INSERT INTO temporada (liga_id, anio_inicio) VALUES (1, 2024);
            INSERT INTO equipo (id, nombre) VALUES (1, 'Equipo A'), (2, 'Equipo B');
            INSERT INTO jugador (id, nombre) VALUES (100, 'Jugador Uno');
            INSERT INTO partido
                (id, temporada_id, fecha, equipo_local_id, equipo_visitante_id, goles_local, goles_visitante)
            VALUES (1, 1, '2024-01-01T15:00:00', 1, 2, 1, 0);
            INSERT INTO disparo
                (id, partido_id, equipo_id, jugador_id, minuto, x, y,
                 resultado, situacion, tipo_disparo, es_gol, xg_understat)
            VALUES (1, 1, 1, 100, 10, 1.0, 0.5, 'Goal', 'OpenPlay', 'RightFoot', 1, 0.5);
            """
        )
        conexion.commit()

        n_actualizados = completar_variables_derivadas(conexion)
        assert n_actualizados == 1

        fila = conexion.execute("SELECT distancia, angulo FROM disparo WHERE id = 1").fetchone()
        assert fila["distancia"] == pytest.approx(0.0)
        assert fila["angulo"] == pytest.approx(math.pi)
    finally:
        conexion.close()
