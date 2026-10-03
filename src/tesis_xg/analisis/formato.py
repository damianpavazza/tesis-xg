from __future__ import annotations


def etiqueta_temporada(anio_inicio: int) -> str:
    """2018 -> "2018/19": las temporadas se guardan por su año de inicio."""
    return f"{anio_inicio}/{(anio_inicio + 1) % 100:02d}"
