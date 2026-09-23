from __future__ import annotations

import math
import sqlite3

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

LARGO_CANCHA_M = 105.0
ANCHO_CANCHA_M = 68.0
ANCHO_ARCO_M = 7.32
MIN_APARICIONES_ACCION_PREVIA = 500


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


def construir_dataset(conexion: sqlite3.Connection, incluir_penales: bool = False) -> pd.DataFrame:
    """Disparos con sus variables derivadas y la temporada a la que
    pertenecen, para entrenar/evaluar el modelo (sección 6.2). Por
    defecto excluye penales: son un caso degenerado (distancia y ángulo
    fijos) que se trata aparte."""
    condicion = "" if incluir_penales else "WHERE d.situacion != 'Penalty'"
    consulta = f"""
        SELECT
            d.id AS disparo_id,
            d.partido_id,
            d.equipo_id,
            d.distancia,
            d.angulo,
            d.situacion,
            d.tipo_disparo,
            d.accion_previa,
            d.es_gol,
            d.xg_understat,
            t.anio_inicio AS temporada
        FROM disparo d
        JOIN partido p ON p.id = d.partido_id
        JOIN temporada t ON t.id = p.temporada_id
        {condicion}
    """
    return pd.read_sql_query(consulta, conexion)


class AgruparCategoriasRaras(BaseEstimator, TransformerMixin):
    """Reemplaza por "Otras" las categorías con menos de `minimo`
    apariciones en el conjunto sobre el que se ajusta (sección 6.2).

    El umbral se aprende solo del conjunto de entrenamiento (`fit`): una
    categoría rara en entrenamiento pero frecuente en prueba no debe
    "verse" antes de tiempo, y una categoría nunca vista en
    entrenamiento cae naturalmente en "Otras".
    """

    def __init__(self, minimo: int = MIN_APARICIONES_ACCION_PREVIA):
        self.minimo = minimo

    def fit(self, X, y=None):
        serie = pd.Series(np.asarray(X).ravel())
        conteos = serie.value_counts()
        self.categorias_frecuentes_ = set(conteos[conteos >= self.minimo].index)
        return self

    def transform(self, X):
        serie = pd.Series(np.asarray(X).ravel())
        transformado = serie.where(serie.isin(self.categorias_frecuentes_), "Otras")
        return transformado.to_numpy().reshape(-1, 1)

    def get_feature_names_out(self, input_features=None):
        # No cambia la cantidad de columnas, solo recodifica valores.
        return np.asarray(input_features, dtype=object)
