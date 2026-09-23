from __future__ import annotations

import math
import sqlite3

LARGO_CANCHA_M = 105.0
ANCHO_CANCHA_M = 68.0
ANCHO_ARCO_M = 7.32


def calcular_distancia_angulo(x: float, y: float) -> tuple[float, float]:
    """Distancia (m) y ángulo de visión del arco (rad) de un disparo.

    `x`, `y` son las coordenadas normalizadas (0-1) que trae Understat,
    con el arco atacado en x=1. Reescala a una cancha reglamentaria de
    105x68m. Ver sección 6.1 de la especificación técnica.
    """
    x_m = x * LARGO_CANCHA_M
    y_m = y * ANCHO_CANCHA_M
    dx = LARGO_CANCHA_M - x_m
    dy = abs(ANCHO_CANCHA_M / 2 - y_m)

    distancia = math.sqrt(dx**2 + dy**2)

    angulo = math.atan2(ANCHO_ARCO_M * dx, dx**2 + dy**2 - (ANCHO_ARCO_M / 2) ** 2)
    if angulo < 0:
        angulo += math.pi

    return distancia, angulo


def completar_variables_derivadas(conexion: sqlite3.Connection) -> int:
    """Calcula y persiste distancia/ángulo para cada fila de `disparo`.

    Devuelve la cantidad de disparos actualizados.
    """
    filas = conexion.execute("SELECT id, x, y FROM disparo").fetchall()
    actualizaciones = [
        (*calcular_distancia_angulo(fila["x"], fila["y"]), fila["id"]) for fila in filas
    ]
    conexion.executemany(
        "UPDATE disparo SET distancia = ?, angulo = ? WHERE id = ?",
        actualizaciones,
    )
    conexion.commit()
    return len(actualizaciones)
