from pathlib import Path

from tesis_xg.almacenamiento import base

TABLAS_ESPERADAS = {
    "liga",
    "temporada",
    "equipo",
    "jugador",
    "partido",
    "equipo_partido",
    "disparo",
}


def test_crear_base_vacia_con_claves_foraneas(tmp_path: Path) -> None:
    ruta_db = tmp_path / "tesis.db"

    conexion = base.crear(ruta_db)
    try:
        assert conexion.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        tablas = {
            fila["name"]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert TABLAS_ESPERADAS <= tablas

        for tabla in TABLAS_ESPERADAS:
            n_filas = conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            assert n_filas == 0
    finally:
        conexion.close()


def test_crear_es_idempotente(tmp_path: Path) -> None:
    ruta_db = tmp_path / "tesis.db"

    base.crear(ruta_db).close()
    conexion = base.crear(ruta_db)  # no debe lanzar excepcion
    conexion.close()
