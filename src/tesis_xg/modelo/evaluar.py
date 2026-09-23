from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from tesis_xg.modelo.entrenar import COLUMNAS_X, TEMPORADAS_PRUEBA
from tesis_xg.modelo.features import construir_dataset

EPSILON_LOG_LOSS = 1e-6


def evaluar(conexion: sqlite3.Connection, directorio_modelos: Path) -> dict:
    """Evalúa el modelo serializado sobre el conjunto de prueba.

    No reporta exactitud ni matriz de confusión (sección 6.4: un
    modelo de xG es un estimador de probabilidad, no un clasificador).
    Persiste las métricas en `<directorio_modelos>/metricas.json`.
    """
    directorio_modelos = Path(directorio_modelos)
    pipeline = joblib.load(directorio_modelos / "modelo_xg.joblib")

    dataset = construir_dataset(conexion, incluir_penales=False)
    prueba = dataset[dataset["temporada"].isin(TEMPORADAS_PRUEBA)].copy()

    y_prueba = prueba["es_gol"].to_numpy()
    xg_propio = pipeline.predict_proba(prueba[COLUMNAS_X])[:, 1]
    xg_understat = prueba["xg_understat"].to_numpy()

    metricas_modelo = {
        "log_loss": float(log_loss(y_prueba, xg_propio)),
        "brier_score": float(brier_score_loss(y_prueba, xg_propio)),
        "roc_auc": float(roc_auc_score(y_prueba, xg_propio)),
    }

    prob_verdadera, prob_predicha = calibration_curve(y_prueba, xg_propio, n_bins=10)
    curva_calibracion = {
        "prob_predicha": prob_predicha.tolist(),
        "prob_verdadera": prob_verdadera.tolist(),
    }

    clasificador = pipeline.named_steps["clasificador"]
    nombres_features = pipeline.named_steps["preprocesador"].get_feature_names_out()
    coeficientes = dict(zip(nombres_features.tolist(), clasificador.coef_[0].tolist()))
    coeficientes["intercepto"] = float(clasificador.intercept_[0])

    # --- Validación por contraste contra el xG del proveedor (sección 6.4) ---
    correlacion_pearson = float(np.corrcoef(xg_propio, xg_understat)[0, 1])

    log_loss_understat = float(
        log_loss(y_prueba, np.clip(xg_understat, EPSILON_LOG_LOSS, 1 - EPSILON_LOG_LOSS))
    )

    prueba["xg_propio"] = xg_propio
    agregado = prueba.groupby(["equipo_id", "temporada"]).agg(
        xg_propio=("xg_propio", "sum"), xg_understat=("xg_understat", "sum")
    )
    mae_agregado_equipo_temporada = float((agregado["xg_propio"] - agregado["xg_understat"]).abs().mean())

    metricas = {
        "n_prueba": len(prueba),
        "modelo": metricas_modelo,
        "curva_calibracion": curva_calibracion,
        "coeficientes": coeficientes,
        "contraste_understat": {
            "correlacion_pearson": correlacion_pearson,
            "log_loss_propio": metricas_modelo["log_loss"],
            "log_loss_understat": log_loss_understat,
            "mae_agregado_equipo_temporada": mae_agregado_equipo_temporada,
        },
    }

    (directorio_modelos / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf8"
    )
    return metricas
