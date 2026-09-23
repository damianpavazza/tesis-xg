from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from tesis_xg.modelo.features import AgruparCategoriasRaras, construir_dataset

logger = logging.getLogger(__name__)

# Partición temporal (sección 6.3): nunca aleatoria, para no filtrar
# información del futuro hacia el pasado.
TEMPORADAS_ENTRENAMIENTO = list(range(2014, 2022))  # 2014/2015 .. 2021/2022
TEMPORADAS_VALIDACION = [2022]  # 2022/2023
TEMPORADAS_PRUEBA = list(range(2023, 2026))  # 2023/2024 .. 2025/2026

COLUMNAS_NUMERICAS = ["distancia", "angulo"]
COLUMNAS_CATEGORICAS_SIMPLES = ["situacion", "tipo_disparo"]
COLUMNA_ACCION_PREVIA = ["accion_previa"]
COLUMNAS_X = COLUMNAS_NUMERICAS + COLUMNAS_CATEGORICAS_SIMPLES + COLUMNA_ACCION_PREVIA

# Grilla chica de regularización: se elige la que minimiza el log loss
# de validación, para darle un uso real a ese conjunto.
VALORES_C_A_PROBAR = [0.01, 0.1, 1.0, 10.0]


def _construir_pipeline(C: float) -> Pipeline:
    preprocesador = ColumnTransformer(
        [
            ("numericas", StandardScaler(), COLUMNAS_NUMERICAS),
            ("situacion", OneHotEncoder(handle_unknown="ignore"), ["situacion"]),
            ("tipo_disparo", OneHotEncoder(handle_unknown="ignore"), ["tipo_disparo"]),
            (
                "accion_previa",
                Pipeline(
                    [
                        ("agrupar", AgruparCategoriasRaras()),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                ["accion_previa"],
            ),
        ]
    )
    return Pipeline(
        [
            ("preprocesador", preprocesador),
            ("clasificador", LogisticRegression(C=C, max_iter=1000)),
        ]
    )


def entrenar(conexion: sqlite3.Connection, directorio_modelos: Path) -> dict:
    """Entrena la regresión logística de línea base y la serializa.

    Devuelve un resumen (tamaños de cada partición, C elegida, tasa de
    conversión de penales) que `evaluar()` y la Etapa 7 reutilizan.
    """
    dataset_completo = construir_dataset(conexion, incluir_penales=True)
    dataset = dataset_completo[dataset_completo["situacion"] != "Penalty"]
    penales = dataset_completo[dataset_completo["situacion"] == "Penalty"]

    entrenamiento = dataset[dataset["temporada"].isin(TEMPORADAS_ENTRENAMIENTO)]
    validacion = dataset[dataset["temporada"].isin(TEMPORADAS_VALIDACION)]
    prueba = dataset[dataset["temporada"].isin(TEMPORADAS_PRUEBA)]

    mejor_c, mejor_log_loss, mejor_pipeline = None, float("inf"), None
    for c in VALORES_C_A_PROBAR:
        pipeline = _construir_pipeline(c)
        pipeline.fit(entrenamiento[COLUMNAS_X], entrenamiento["es_gol"])
        p_validacion = pipeline.predict_proba(validacion[COLUMNAS_X])[:, 1]
        perdida = log_loss(validacion["es_gol"], p_validacion)
        logger.info("C=%s -> log loss de validación=%.5f", c, perdida)
        if perdida < mejor_log_loss:
            mejor_c, mejor_log_loss, mejor_pipeline = c, perdida, pipeline

    penales_entrenamiento = penales[penales["temporada"].isin(TEMPORADAS_ENTRENAMIENTO)]
    tasa_conversion_penales = float(penales_entrenamiento["es_gol"].mean())

    directorio_modelos = Path(directorio_modelos)
    directorio_modelos.mkdir(parents=True, exist_ok=True)
    joblib.dump(mejor_pipeline, directorio_modelos / "modelo_xg.joblib")

    return {
        "n_entrenamiento": len(entrenamiento),
        "n_validacion": len(validacion),
        "n_prueba": len(prueba),
        "n_penales_entrenamiento": len(penales_entrenamiento),
        "n_penales_total": len(penales),
        "tasa_conversion_penales": tasa_conversion_penales,
        "C_elegida": mejor_c,
        "log_loss_validacion": mejor_log_loss,
        "temporadas_entrenamiento": TEMPORADAS_ENTRENAMIENTO,
        "temporadas_validacion": TEMPORADAS_VALIDACION,
        "temporadas_prueba": TEMPORADAS_PRUEBA,
    }
