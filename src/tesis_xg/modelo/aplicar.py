from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import joblib

from tesis_xg.modelo.entrenar import COLUMNAS_X
from tesis_xg.modelo.features import construir_dataset


def calcular_xg_propio(conexion: sqlite3.Connection, directorio_modelos: Path) -> dict:
    """Completa `disparo.xg_propio` para toda la tabla (sección 6.3): los
    disparos no-penal reciben la probabilidad del modelo entrenado; los
    penales reciben la tasa de conversión histórica de penales calculada
    durante el entrenamiento (son un caso degenerado que se excluye del
    ajuste, ver sección 6.2).
    """
    directorio_modelos = Path(directorio_modelos)
    pipeline = joblib.load(directorio_modelos / "modelo_xg.joblib")
    info_entrenamiento = json.loads(
        (directorio_modelos / "entrenamiento_info.json").read_text(encoding="utf8")
    )
    tasa_conversion_penales = info_entrenamiento["tasa_conversion_penales"]

    dataset = construir_dataset(conexion, incluir_penales=True)
    no_penales = dataset[dataset["situacion"] != "Penalty"]
    penales = dataset[dataset["situacion"] == "Penalty"]

    xg_no_penales = pipeline.predict_proba(no_penales[COLUMNAS_X])[:, 1]

    actualizaciones = list(zip(xg_no_penales.tolist(), no_penales["disparo_id"].tolist()))
    actualizaciones += [
        (tasa_conversion_penales, disparo_id) for disparo_id in penales["disparo_id"].tolist()
    ]

    conexion.executemany("UPDATE disparo SET xg_propio = ? WHERE id = ?", actualizaciones)
    conexion.commit()

    return {
        "n_no_penales": len(no_penales),
        "n_penales": len(penales),
        "tasa_conversion_penales_usada": tasa_conversion_penales,
    }
