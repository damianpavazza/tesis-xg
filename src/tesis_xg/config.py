from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RutasConfig:
    cache: Path
    base_datos: Path
    modelos: Path


@dataclass(frozen=True)
class HttpConfig:
    espera_entre_solicitudes: float
    reintentos: int


@dataclass(frozen=True)
class LigasConfig:
    codigos: list[str]
    temporada_desde: int
    temporada_hasta: int


@dataclass(frozen=True)
class Config:
    rutas: RutasConfig
    http: HttpConfig
    ligas: LigasConfig


def cargar_config(ruta: Path | None = None) -> Config:
    """Lee config.toml y resuelve las rutas relativas a su ubicación."""
    ruta = ruta or (RAIZ_PROYECTO / "config.toml")
    with ruta.open("rb") as archivo:
        datos = tomllib.load(archivo)

    raiz = ruta.parent
    rutas = datos["rutas"]

    return Config(
        rutas=RutasConfig(
            cache=raiz / rutas["cache"],
            base_datos=raiz / rutas["base_datos"],
            modelos=raiz / rutas["modelos"],
        ),
        http=HttpConfig(**datos["http"]),
        ligas=LigasConfig(**datos["ligas"]),
    )
