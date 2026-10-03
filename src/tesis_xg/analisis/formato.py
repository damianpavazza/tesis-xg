from __future__ import annotations


def etiqueta_temporada(anio_inicio: int) -> str:
    """2018 -> "2018/19": las temporadas se guardan por su año de inicio."""
    return f"{anio_inicio}/{(anio_inicio + 1) % 100:02d}"


# Etiquetas en español de las categorías que Understat informa en inglés
# (situacion, tipo_disparo, resultado) y de las zonas de tiro, que se
# calculan en `analisis/jugadores.py`.
ETIQUETAS_SITUACION = {
    "OpenPlay": "Juego abierto",
    "FromCorner": "Tiro de esquina",
    "SetPiece": "Pelota parada",
    "DirectFreekick": "Tiro libre directo",
    "Penalty": "Penal",
}
ETIQUETAS_TIPO_DISPARO = {
    "LeftFoot": "Pie izquierdo",
    "RightFoot": "Pie derecho",
    "Head": "Cabeza",
    "OtherBodyPart": "Otra parte del cuerpo",
}
ETIQUETAS_RESULTADO = {
    "Goal": "Gol",
    "OwnGoal": "Gol en contra",
    "ShotOnPost": "Poste",
    "SavedShot": "Atajado",
    "BlockedShot": "Bloqueado",
    "MissedShots": "Desviado",
}
ETIQUETAS_ZONA = {
    "area_chica": "Área chica",
    "area_grande": "Área grande",
    "fuera_del_area": "Fuera del área",
}
