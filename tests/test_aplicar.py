import random
from pathlib import Path

import pytest

from tesis_xg.almacenamiento import base
from tesis_xg.modelo import entrenar as entrenar_modulo
from tesis_xg.modelo.aplicar import calcular_xg_propio
from tesis_xg.modelo.features import completar_variables_derivadas

SITUACIONES_NO_PENAL = ["OpenPlay", "FromCorner", "SetPiece", "DirectFreekick"]
TIPOS_DISPARO = ["RightFoot", "LeftFoot", "Head"]
ACCIONES_PREVIAS = ["Pass", "Cross", "None"]


def _poblar_disparos_sinteticos(conexion, n_no_penal: int = 300, n_penales: int = 20) -> None:
    conexion.executescript(
        """
        INSERT INTO liga (codigo, nombre, pais) VALUES ('EPL', 'Premier League', 'Inglaterra');
        INSERT INTO temporada (liga_id, anio_inicio) VALUES (1, 2014), (1, 2022), (1, 2023);
        INSERT INTO equipo (id, nombre) VALUES (1, 'Equipo A'), (2, 'Equipo B');
        INSERT INTO jugador (id, nombre) VALUES (100, 'Jugador Uno');
        """
    )
    # Un partido por temporada, para que cada particion temporal tenga datos.
    for temporada_id, partido_id in ((1, 1), (2, 2), (3, 3)):
        conexion.execute(
            """
            INSERT INTO partido
                (id, temporada_id, fecha, equipo_local_id, equipo_visitante_id, goles_local, goles_visitante)
            VALUES (?, ?, '2024-01-01T15:00:00', 1, 2, 1, 0)
            """,
            (partido_id, temporada_id),
        )

    random.seed(0)
    disparo_id = 1
    filas = []
    for _ in range(n_no_penal):
        partido_id = random.choice((1, 2, 3))
        es_gol = 1 if random.random() < 0.1 else 0
        filas.append(
            (
                disparo_id, partido_id, 1, 100,
                random.randint(1, 90), random.uniform(0.5, 1.0), random.uniform(0.0, 1.0),
                "Goal" if es_gol else "MissedShots",
                random.choice(SITUACIONES_NO_PENAL),
                random.choice(TIPOS_DISPARO),
                random.choice(ACCIONES_PREVIAS),
                es_gol, random.uniform(0.02, 0.4),
            )
        )
        disparo_id += 1
    for _ in range(n_penales):
        partido_id = random.choice((1, 2, 3))
        es_gol = 1 if random.random() < 0.78 else 0
        filas.append(
            (
                disparo_id, partido_id, 1, 100,
                random.randint(1, 90), 0.885, 0.5,
                "Goal" if es_gol else "SavedShot",
                "Penalty", "RightFoot", "None",
                es_gol, 0.76,
            )
        )
        disparo_id += 1

    conexion.executemany(
        """
        INSERT INTO disparo
            (id, partido_id, equipo_id, jugador_id, minuto, x, y,
             resultado, situacion, tipo_disparo, accion_previa, es_gol, xg_understat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        filas,
    )
    conexion.commit()


def test_calcular_xg_propio_completa_toda_la_tabla(tmp_path: Path, monkeypatch) -> None:
    conexion = base.crear(tmp_path / "tesis.db")
    try:
        _poblar_disparos_sinteticos(conexion)
        completar_variables_derivadas(conexion)

        # Particion temporal chica para que las 3 temporadas sinteticas
        # (2014, 2022, 2023) caigan una en cada conjunto.
        monkeypatch.setattr(entrenar_modulo, "TEMPORADAS_ENTRENAMIENTO", [2014])
        monkeypatch.setattr(entrenar_modulo, "TEMPORADAS_VALIDACION", [2022])
        monkeypatch.setattr(entrenar_modulo, "TEMPORADAS_PRUEBA", [2023])
        monkeypatch.setattr(entrenar_modulo, "VALORES_C_A_PROBAR", [1.0])

        directorio_modelos = tmp_path / "modelos"
        info = entrenar_modulo.entrenar(conexion, directorio_modelos)

        resultado = calcular_xg_propio(conexion, directorio_modelos)
        assert resultado["n_penales"] == 20
        assert resultado["tasa_conversion_penales_usada"] == pytest.approx(
            info["tasa_conversion_penales"]
        )

        (n_sin_valor,) = conexion.execute(
            "SELECT COUNT(*) FROM disparo WHERE xg_propio IS NULL"
        ).fetchone()
        assert n_sin_valor == 0

        xg_penales = [
            fila[0]
            for fila in conexion.execute(
                "SELECT DISTINCT xg_propio FROM disparo WHERE situacion = 'Penalty'"
            )
        ]
        assert xg_penales == [pytest.approx(info["tasa_conversion_penales"])]

        (min_xg, max_xg) = conexion.execute(
            "SELECT MIN(xg_propio), MAX(xg_propio) FROM disparo WHERE situacion != 'Penalty'"
        ).fetchone()
        assert 0.0 <= min_xg <= max_xg <= 1.0
    finally:
        conexion.close()
