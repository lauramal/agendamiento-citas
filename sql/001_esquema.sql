-- =====================================================================
-- Agendamiento de citas médicas — esquema
-- Principio: las reglas que evitan inconsistencias viven en la base de
-- datos, no solo en el código. Ningún canal (web, agente, WhatsApp,
-- call center) puede saltárselas, ni siquiera con acceso directo.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS btree_gist;   -- necesario para las restricciones anti-traslape

-- ---------- Catálogos ----------
CREATE TABLE centros (
    id              BIGSERIAL PRIMARY KEY,
    nombre          TEXT NOT NULL UNIQUE,
    direccion       TEXT NOT NULL,
    ciudad          TEXT NOT NULL,
    telefono        TEXT,
    hora_apertura   TIME NOT NULL DEFAULT '07:00',
    hora_cierre     TIME NOT NULL DEFAULT '18:00',
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT horario_valido CHECK (hora_cierre > hora_apertura)
);

CREATE TABLE salas (
    id          BIGSERIAL PRIMARY KEY,
    centro_id   BIGINT NOT NULL REFERENCES centros(id),
    nombre      TEXT NOT NULL,
    tipo        TEXT NOT NULL DEFAULT 'consultorio',
    activo      BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sala_unica_por_centro UNIQUE (centro_id, nombre),
    CONSTRAINT sala_centro UNIQUE (id, centro_id)   -- permite la FK compuesta desde citas
);

CREATE TABLE medicos (
    id              BIGSERIAL PRIMARY KEY,
    documento       TEXT NOT NULL UNIQUE,
    nombres         TEXT NOT NULL,
    apellidos       TEXT NOT NULL,
    especialidad    TEXT NOT NULL,
    email           TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Accesibilidad como dato: cómo prefiere el paciente que lo contacten
-- y si necesita atención asistida (mensajes simples, acompañamiento).
CREATE TABLE pacientes (
    id                  BIGSERIAL PRIMARY KEY,
    documento           TEXT NOT NULL UNIQUE,
    nombres             TEXT NOT NULL,
    apellidos           TEXT NOT NULL,
    fecha_nacimiento    DATE NOT NULL,
    email               TEXT,
    telefono            TEXT,
    canal_preferido     TEXT NOT NULL DEFAULT 'email'
                        CHECK (canal_preferido IN ('email','whatsapp','llamada')),
    atencion_asistida   BOOLEAN NOT NULL DEFAULT FALSE,
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT contacto_minimo CHECK (email IS NOT NULL OR telefono IS NOT NULL)
);

-- ---------- Citas ----------
-- Estados:
--   ofrecida    cupo reservado temporalmente para alguien de la lista de espera
--   programada  agendada, sin confirmar
--   confirmada  el paciente confirmó (desde el recordatorio o el agente)
--   cancelada / atendida / no_asistio   estados finales
-- Solo 'ofrecida', 'programada' y 'confirmada' ocupan el cupo.
CREATE TABLE citas (
    id                  BIGSERIAL PRIMARY KEY,
    paciente_id         BIGINT NOT NULL REFERENCES pacientes(id),
    medico_id           BIGINT NOT NULL REFERENCES medicos(id),
    centro_id           BIGINT NOT NULL,
    sala_id             BIGINT NOT NULL,
    inicio              TIMESTAMPTZ NOT NULL,
    fin                 TIMESTAMPTZ NOT NULL,
    duracion_min        INT NOT NULL CHECK (duracion_min BETWEEN 10 AND 240),
    estado              TEXT NOT NULL DEFAULT 'programada'
                        CHECK (estado IN ('ofrecida','programada','confirmada','cancelada','atendida','no_asistio')),
    motivo_consulta     TEXT,
    motivo_cancelacion  TEXT,
    canal_origen        TEXT NOT NULL DEFAULT 'api'
                        CHECK (canal_origen IN ('api','web','agente','whatsapp','lista_espera','call_center')),
    oferta_expira_en    TIMESTAMPTZ,
    recordatorio_enviado_en TIMESTAMPTZ,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- La sala debe pertenecer al centro de la cita (FK compuesta)
    CONSTRAINT sala_del_centro FOREIGN KEY (sala_id, centro_id) REFERENCES salas(id, centro_id),
    CONSTRAINT rango_valido CHECK (fin > inicio),
    CONSTRAINT cancelar_con_motivo CHECK (estado <> 'cancelada' OR motivo_cancelacion IS NOT NULL),
    CONSTRAINT oferta_con_expiracion CHECK (estado <> 'ofrecida' OR oferta_expira_en IS NOT NULL),

    -- Anti-traslape: un médico, una sala o un paciente no pueden tener
    -- dos citas activas que se crucen en el tiempo. La base de datos lo
    -- garantiza incluso con dos reservas simultáneas (sin condiciones de carrera).
    CONSTRAINT medico_sin_traslape EXCLUDE USING gist
        (medico_id WITH =, tstzrange(inicio, fin, '[)') WITH &&)
        WHERE (estado IN ('ofrecida','programada','confirmada')),
    CONSTRAINT sala_sin_traslape EXCLUDE USING gist
        (sala_id WITH =, tstzrange(inicio, fin, '[)') WITH &&)
        WHERE (estado IN ('ofrecida','programada','confirmada')),
    CONSTRAINT paciente_sin_traslape EXCLUDE USING gist
        (paciente_id WITH =, tstzrange(inicio, fin, '[)') WITH &&)
        WHERE (estado IN ('ofrecida','programada','confirmada'))
);
CREATE INDEX citas_paciente ON citas (paciente_id, inicio);
CREATE INDEX citas_centro   ON citas (centro_id, inicio);
CREATE INDEX citas_sala     ON citas (sala_id, inicio);

-- Historial de estados: nada se borra, todo se explica
CREATE TABLE citas_historial (
    id              BIGSERIAL PRIMARY KEY,
    cita_id         BIGINT NOT NULL REFERENCES citas(id),
    estado_anterior TEXT,
    estado_nuevo    TEXT NOT NULL,
    detalle         TEXT,
    canal           TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Lista de espera ----------
-- Cuando no hay cupo, el paciente queda en fila. Si alguien cancela,
-- el sistema le ofrece el cupo al primero que encaje y se lo reserva
-- por un tiempo corto; si no acepta, pasa al siguiente.
CREATE TABLE lista_espera (
    id              BIGSERIAL PRIMARY KEY,
    paciente_id     BIGINT NOT NULL REFERENCES pacientes(id),
    especialidad    TEXT NOT NULL,
    medico_id       BIGINT REFERENCES medicos(id),     -- opcional: "con cualquier médico"
    centro_id       BIGINT REFERENCES centros(id),     -- opcional: "en cualquier centro"
    desde           DATE NOT NULL,
    hasta           DATE NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'esperando'
                    CHECK (estado IN ('esperando','ofrecida','asignada','expirada','retirada')),
    cita_ofrecida_id BIGINT REFERENCES citas(id),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT rango_espera CHECK (hasta >= desde)
);
CREATE INDEX espera_activa ON lista_espera (especialidad, estado, creado_en);

-- ---------- Notificaciones (trazabilidad de todo lo enviado) ----------
CREATE TABLE notificaciones (
    id          BIGSERIAL PRIMARY KEY,
    paciente_id BIGINT NOT NULL REFERENCES pacientes(id),
    cita_id     BIGINT REFERENCES citas(id),
    canal       TEXT NOT NULL,
    tipo        TEXT NOT NULL,   -- recordatorio | oferta_lista_espera | confirmacion | cancelacion
    destino     TEXT,
    estado      TEXT NOT NULL CHECK (estado IN ('enviada','fallida','simulada')),
    detalle     TEXT,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);
