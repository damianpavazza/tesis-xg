from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class ClienteHTTP:
    """Trae JSON de una URL con control de tasa, reintentos y caché en disco.

    Responsabilidad única: el resto del sistema da por sentado que, si el
    JSON ya está en caché, no se toca la red; y que un 404 no se reintenta.
    """

    def __init__(
        self,
        directorio_cache: Path,
        espera_entre_solicitudes: float = 1.0,
        reintentos: int = 3,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.directorio_cache = Path(directorio_cache)
        self.directorio_cache.mkdir(parents=True, exist_ok=True)
        self.espera_entre_solicitudes = espera_entre_solicitudes
        self.reintentos = reintentos
        self.headers = headers or {}
        self._sesion = requests.Session()

    def obtener_json(self, url: str, nombre_cache: str, forzar: bool = False) -> dict:
        ruta_cache = self.directorio_cache / nombre_cache

        if not forzar and ruta_cache.exists():
            logger.debug("cache: %s", nombre_cache)
            return json.loads(ruta_cache.read_text(encoding="utf8"))

        datos = self._solicitar(url)
        ruta_cache.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf8")
        logger.info("red: %s -> %s", url, nombre_cache)
        return datos

    def _solicitar(self, url: str) -> dict:
        ultimo_error: Exception | None = None

        for intento in range(1, self.reintentos + 1):
            try:
                respuesta = self._sesion.get(url, headers=self.headers, timeout=20)
            except requests.RequestException as exc:
                ultimo_error = exc
            else:
                if respuesta.status_code == 404:
                    respuesta.raise_for_status()

                if respuesta.status_code < 500:
                    respuesta.raise_for_status()
                    time.sleep(self.espera_entre_solicitudes)
                    return respuesta.json()

                ultimo_error = requests.HTTPError(
                    f"{respuesta.status_code} en {url}", response=respuesta
                )

            if intento < self.reintentos:
                espera_backoff = self.espera_entre_solicitudes * (2 ** (intento - 1))
                logger.warning(
                    "intento %d/%d falló para %s (%s); reintento en %.1fs",
                    intento,
                    self.reintentos,
                    url,
                    ultimo_error,
                    espera_backoff,
                )
                time.sleep(espera_backoff)

        assert ultimo_error is not None
        raise ultimo_error
