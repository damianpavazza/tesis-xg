import json
from pathlib import Path

from tesis_xg.almacenamiento import base, carga

LIGA_JSON = {
    "teams": {
        "10": {
            "id": "10",
            "title": "Equipo A",
            "history": [
                {
                    "h_a": "h", "xG": 1.1, "xGA": 0.5, "npxG": 1.1, "npxGA": 0.5,
                    "ppda": {"att": 100, "def": 10},
                    "ppda_allowed": {"att": 50, "def": 0},
                    "deep": 3, "deep_allowed": 1, "scored": 2, "missed": 0,
                    "xpts": 1.8, "result": "w", "date": "2024-01-01 15:00:00",
                    "wins": 1, "draws": 0, "loses": 0, "pts": 3, "npxGD": 0.6,
                }
            ],
        },
        "20": {
            "id": "20",
            "title": "Equipo B",
            "history": [
                {
                    "h_a": "a", "xG": 0.5, "xGA": 1.1, "npxG": 0.5, "npxGA": 1.1,
                    "ppda": {"att": 50, "def": 0},
                    "ppda_allowed": {"att": 100, "def": 10},
                    "deep": 1, "deep_allowed": 3, "scored": 0, "missed": 2,
                    "xpts": 0.3, "result": "l", "date": "2024-01-01 15:00:00",
                    "wins": 0, "draws": 0, "loses": 1, "pts": 0, "npxGD": -0.6,
                }
            ],
        },
    },
    "players": [
        {"id": "100", "player_name": "Jugador Uno"},
        {"id": "200", "player_name": "Jugador Dos"},
    ],
    "dates": [
        {
            "id": "555", "isResult": True,
            "h": {"id": "10", "title": "Equipo A"},
            "a": {"id": "20", "title": "Equipo B"},
            "goals": {"h": "2", "a": "0"},
            "datetime": "2024-01-01 15:00:00",
        }
    ],
}

PARTIDO_JSON = {
    "rosters": {
        "h": {"100": {"player_id": "100", "player": "Jugador Uno"}},
        "a": {"200": {"player_id": "200", "player": "Jugador Dos"}},
    },
    "shots": {
        "h": [
            {
                "id": "9001", "minute": "10", "result": "Goal", "X": "0.9", "Y": "0.5",
                "xG": "0.3", "player": "Jugador Uno", "h_a": "h", "player_id": "100",
                "situation": "OpenPlay", "shotType": "RightFoot", "match_id": "555",
                "player_assisted": None, "lastAction": "None",
            },
            {
                "id": "9002", "minute": "20", "result": "SavedShot", "X": "0.8", "Y": "0.4",
                "xG": "0.1", "player": "Jugador Uno", "h_a": "h", "player_id": "100",
                "situation": "OpenPlay", "shotType": "LeftFoot", "match_id": "555",
                "player_assisted": "Jugador Dos", "lastAction": "Pass",
            },
        ],
        "a": [],
    },
}


def _preparar_cache(directorio: Path) -> None:
    (directorio / "liga_EPL_2024.json").write_text(json.dumps(LIGA_JSON), encoding="utf8")
    (directorio / "partido_555.json").write_text(json.dumps(PARTIDO_JSON), encoding="utf8")


def test_cargar_todo_transforma_correctamente(tmp_path: Path) -> None:
    _preparar_cache(tmp_path)
    conexion = base.crear(tmp_path / "tesis.db")
    try:
        carga.cargar_todo(conexion, tmp_path)

        partido = conexion.execute("SELECT * FROM partido WHERE id = 555").fetchone()
        assert partido["fecha"] == "2024-01-01T15:00:00"
        assert partido["goles_local"] == 2 and partido["goles_visitante"] == 0

        equipo_a = conexion.execute(
            "SELECT * FROM equipo_partido WHERE partido_id = 555 AND equipo_id = 10"
        ).fetchone()
        assert equipo_a["ppda_coef"] == 10.0        # 100 / 10
        assert equipo_a["oppda_coef"] is None        # def == 0 -> NULL, no division por cero

        equipo_b = conexion.execute(
            "SELECT * FROM equipo_partido WHERE partido_id = 555 AND equipo_id = 20"
        ).fetchone()
        assert equipo_b["ppda_coef"] is None
        assert equipo_b["oppda_coef"] == 10.0

        gol = conexion.execute("SELECT * FROM disparo WHERE id = 9001").fetchone()
        assert gol["es_gol"] == 1
        assert gol["jugador_asistencia_id"] is None
        assert gol["accion_previa"] == "None"        # categoria valida, no NULL

        con_asistencia = conexion.execute("SELECT * FROM disparo WHERE id = 9002").fetchone()
        assert con_asistencia["es_gol"] == 0
        assert con_asistencia["jugador_asistencia_id"] == 200  # resuelto por nombre via roster

        (n_disparos,) = conexion.execute("SELECT COUNT(*) FROM disparo").fetchone()
        assert n_disparos == 2
    finally:
        conexion.close()


def test_cargar_todo_es_idempotente(tmp_path: Path) -> None:
    _preparar_cache(tmp_path)
    conexion = base.crear(tmp_path / "tesis.db")
    try:
        carga.cargar_todo(conexion, tmp_path)
        carga.cargar_todo(conexion, tmp_path)

        (n_disparos,) = conexion.execute("SELECT COUNT(*) FROM disparo").fetchone()
        (n_partidos,) = conexion.execute("SELECT COUNT(*) FROM partido").fetchone()
        (n_equipo_partido,) = conexion.execute("SELECT COUNT(*) FROM equipo_partido").fetchone()

        assert n_disparos == 2
        assert n_partidos == 1
        assert n_equipo_partido == 2
    finally:
        conexion.close()


def test_recargar_no_borra_xg_propio(tmp_path: Path) -> None:
    """xg_propio lo completa la etapa de modelo: recargar desde la cache
    (p.ej. tras agregar mas partidos) no debe pisarlo con NULL."""
    _preparar_cache(tmp_path)
    conexion = base.crear(tmp_path / "tesis.db")
    try:
        carga.cargar_todo(conexion, tmp_path)
        conexion.execute("UPDATE disparo SET xg_propio = 0.42 WHERE id = 9001")
        conexion.commit()

        carga.cargar_todo(conexion, tmp_path)

        xg_propio = conexion.execute(
            "SELECT xg_propio FROM disparo WHERE id = 9001"
        ).fetchone()[0]
        assert xg_propio == 0.42
    finally:
        conexion.close()
