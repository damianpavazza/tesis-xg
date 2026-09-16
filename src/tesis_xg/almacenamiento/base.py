from __future__ import annotations

import sqlite3
from pathlib import Path

RUTA_ESQUEMA = Path(__file__).resolve().parent / "esquema.sql"


def conectar(ruta_base_datos: Path) -> sqlite3.Connection:
    """Abre una conexión con claves foráneas activas.

    `foreign_keys` es un ajuste por conexión en SQLite, no se persiste en
    el archivo: hay que activarlo cada vez que se abre la base.
    """
    conexion = sqlite3.connect(ruta_base_datos)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.row_factory = sqlite3.Row
    return conexion


def crear(ruta_base_datos: Path) -> sqlite3.Connection:
    """Crea el archivo de base de datos (si no existe) y aplica el esquema."""
    ruta_base_datos = Path(ruta_base_datos)
    ruta_base_datos.parent.mkdir(parents=True, exist_ok=True)
    conexion = conectar(ruta_base_datos)
    migrar(conexion)
    return conexion


def migrar(conexion: sqlite3.Connection) -> None:
    """Aplica el esquema actual. Idempotente: seguro de correr sobre una
    base ya creada (todas las sentencias usan `IF NOT EXISTS`)."""
    esquema_sql = RUTA_ESQUEMA.read_text(encoding="utf8")
    conexion.executescript(esquema_sql)
    conexion.commit()
