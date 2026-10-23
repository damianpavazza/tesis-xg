PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS liga (
    id      INTEGER PRIMARY KEY,
    codigo  TEXT NOT NULL UNIQUE,
    nombre  TEXT NOT NULL,
    pais    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS temporada (
    id          INTEGER PRIMARY KEY,
    liga_id     INTEGER NOT NULL REFERENCES liga(id),
    anio_inicio INTEGER NOT NULL,
    UNIQUE (liga_id, anio_inicio)
);

CREATE TABLE IF NOT EXISTS equipo (
    id     INTEGER PRIMARY KEY,          -- id de Understat
    nombre TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jugador (
    id     INTEGER PRIMARY KEY,          -- id de Understat
    nombre TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS partido (
    id                  INTEGER PRIMARY KEY,   -- id de Understat
    temporada_id        INTEGER NOT NULL REFERENCES temporada(id),
    fecha               TEXT    NOT NULL,      -- ISO-8601
    equipo_local_id     INTEGER NOT NULL REFERENCES equipo(id),
    equipo_visitante_id INTEGER NOT NULL REFERENCES equipo(id),
    goles_local         INTEGER,
    goles_visitante     INTEGER
);

CREATE TABLE IF NOT EXISTS equipo_partido (
    partido_id       INTEGER NOT NULL REFERENCES partido(id),
    equipo_id        INTEGER NOT NULL REFERENCES equipo(id),
    condicion        TEXT    NOT NULL CHECK (condicion IN ('h','a')),
    xg               REAL,
    xga              REAL,
    npxg             REAL,
    npxga            REAL,
    npxgd            REAL,
    ppda_att         INTEGER,
    ppda_def         INTEGER,
    ppda_coef        REAL,
    oppda_att        INTEGER,
    oppda_def        INTEGER,
    oppda_coef       REAL,
    deep             INTEGER,
    deep_allowed     INTEGER,
    goles            INTEGER,
    goles_recibidos  INTEGER,
    xpts             REAL,
    puntos           INTEGER,
    resultado        TEXT CHECK (resultado IN ('w','d','l')),
    PRIMARY KEY (partido_id, equipo_id)
);

CREATE TABLE IF NOT EXISTS disparo (
    id                    INTEGER PRIMARY KEY,   -- id de Understat
    partido_id            INTEGER NOT NULL REFERENCES partido(id),
    equipo_id             INTEGER NOT NULL REFERENCES equipo(id),
    jugador_id            INTEGER REFERENCES jugador(id),
    jugador_asistencia_id INTEGER REFERENCES jugador(id),
    minuto                INTEGER NOT NULL,
    x                     REAL    NOT NULL,      -- normalizada 0-1
    y                     REAL    NOT NULL,
    resultado             TEXT    NOT NULL,
    situacion             TEXT    NOT NULL,
    tipo_disparo          TEXT    NOT NULL,
    accion_previa         TEXT,
    es_gol                INTEGER NOT NULL CHECK (es_gol IN (0,1)),
    distancia             REAL,                  -- derivada, metros
    angulo                REAL,                  -- derivada, radianes
    xg_understat          REAL    NOT NULL,
    xg_propio             REAL
);

CREATE INDEX IF NOT EXISTS idx_disparo_partido  ON disparo(partido_id);
CREATE INDEX IF NOT EXISTS idx_disparo_jugador  ON disparo(jugador_id);
CREATE INDEX IF NOT EXISTS idx_partido_temporada ON partido(temporada_id);

-- No está en la especificación original (sección 4): se agregó en la
-- Etapa 8 porque la sección 7 pide "goles contra xG por jugador y
-- temporada, con mínimo de minutos configurable", y ese mínimo de
-- minutos no tiene dónde vivir sin esta tabla. Viene del arreglo
-- `players` de `getLeagueData`, que ya se descarga y cachea pero hasta
-- ahora solo se usaba para poblar `jugador` (id + nombre).
CREATE TABLE IF NOT EXISTS jugador_temporada (
    jugador_id    INTEGER NOT NULL REFERENCES jugador(id),
    temporada_id  INTEGER NOT NULL REFERENCES temporada(id),
    equipo        TEXT,
    posicion      TEXT,
    partidos      INTEGER,
    minutos       INTEGER,
    goles         INTEGER,
    goles_np      INTEGER,
    asistencias   INTEGER,
    xg            REAL,
    xg_np         REAL,
    xa            REAL,
    disparos      INTEGER,
    pases_clave   INTEGER,
    PRIMARY KEY (jugador_id, temporada_id)
);
