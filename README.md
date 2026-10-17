# Agendamiento de Citas Médicas

**Una sola fuente de cupos para todos los canales, con un asistente conversacional que recupera las citas que se iban a perder**

Sistema para gestionar sedes, salas, médicos, pacientes y citas, donde ningún canal puede crear citas inconsistentes y los cupos que se liberan llegan solos a quien los está esperando.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.143-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangChain-LangGraph-1C3C3C?style=flat&logo=langchain&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/pruebas-33%20pasando-2F7D5B?style=flat)

---

## El problema detrás del enunciado

El enunciado pide un CRUD con citas y validaciones. Antes de diseñar me pregunté por qué el agendamiento falla en la práctica:

- **Cupos perdidos.** La gente no avisa que no va, mientras otros esperan turno sin conseguirlo.
- **Inventario por canal.** Por WhatsApp "hay más citas" que en la web. No es un problema de la app: cada canal reparte cupos por su lado.
- **Apps que excluyen.** Los adultos mayores, que más citas necesitan, son quienes menos saben usarlas.

La solución cumple el enunciado y responde a estas tres causas.

---

## Características Principales

- **CRUD completo**: pacientes, médicos, sedes y salas, con borrado lógico
- **Citas con estados**: programada, confirmada, ofrecida, cancelada, atendida, no asistió
- **Cero cruces garantizados por la base de datos**: médico, sala y paciente, incluso con reservas simultáneas
- **Disponibilidad única**: la misma fuente de cupos para la API, la web y el asistente
- **Lista de espera automática**: el cupo liberado se reserva al primero de la fila
- **Recordatorios**: confirmar o cancelar en un clic desde el correo
- **Asistente Nora**: agente con LangChain y LangGraph que agenda, cancela y ofrece la lista de espera
- **Accesibilidad como dato**: canal preferido y atención asistida por paciente
- **33 pruebas automáticas**, incluida una de concurrencia

---

## Arquitectura del Sistema

```mermaid
graph TB
    subgraph "Canales"
        W[Página web del paciente]
        A[Asistente Nora<br/>LangChain + LangGraph]
        C[Correo<br/>enlaces firmados]
        WA[WhatsApp / call center<br/>adaptador futuro]
    end

    subgraph "Backend · FastAPI"
        API[API REST]
        S[Servicios de negocio<br/>citas · disponibilidad · lista de espera]
        J[Tareas automáticas<br/>recordatorios · ofertas]
        N[Notificaciones<br/>email · WhatsApp · llamada]
    end

    subgraph "Datos"
        DB[(PostgreSQL<br/>reglas en el esquema)]
    end

    W --> API
    C --> API
    WA -.-> API
    API --> S
    A --> S
    J --> S
    S --> DB
    S --> N
```

**Tres principios:**

1. **Una sola fuente de verdad.** Todos los canales, incluido el asistente, usan los mismos servicios. Si un cupo existe, existe para todos.
2. **Validación en dos capas.** El servicio da mensajes claros y aplica reglas de contexto; la base de datos garantiza lo que nunca puede romperse.
3. **El asistente no tiene privilegios.** Si intenta algo inválido, recibe el mismo rechazo que cualquier canal y se lo explica al paciente.

### Estructura del Proyecto

```
agendamiento-citas/
├── sql/
│   └── 001_esquema.sql          # Esquema con todas sus restricciones
│
├── app/
│   ├── services/                # Reglas de negocio
│   │   ├── citas.py             # Agendar, cancelar, reprogramar, estados
│   │   ├── disponibilidad.py    # Fuente única de cupos
│   │   ├── lista_espera.py      # Ofertas, aceptar, rechazar, vencer
│   │   ├── notificaciones.py    # Canales y plantillas de mensajes
│   │   └── tokens.py            # Enlaces firmados del correo
│   ├── routers/                 # Endpoints REST
│   ├── agente/nora.py          # Asistente conversacional
│   ├── static/index.html        # Página accesible del paciente
│   └── jobs.py                  # Recordatorios y vencimiento de ofertas
│
├── .claude/skills/              # Skills: nueva regla de negocio y registrar decisión
├── tests/                       # 33 pruebas automáticas
├── docs/decisiones.md           # Cada decisión con sus alternativas
├── scripts/semilla.py           # Datos de demostración
└── docker-compose.yml           # PostgreSQL + Mailpit + API
```

---

## Flujos Principales

### 1. Un cupo cancelado llega a la lista de espera

```mermaid
sequenceDiagram
    participant D as Daniel
    participant API as API
    participant LE as Lista de espera
    participant DB as PostgreSQL
    participant G as Gloria

    D->>API: Cancela su cita (con motivo)
    API->>DB: Cita → cancelada
    API->>LE: Ofrecer el cupo liberado
    LE->>DB: Busca al primero de la fila que encaje
    LE->>DB: Crea cita "ofrecida" (bloquea el cupo 2 h)
    LE->>G: "Se liberó una cita para usted"
    alt Acepta
        G->>API: Tomar esta cita
        API->>DB: Cita → confirmada
    else Rechaza o no responde
        API->>LE: El cupo pasa al siguiente de la fila
    end
```

### 2. El asistente agenda una cita

```mermaid
sequenceDiagram
    participant P as Paciente
    participant S as Nora (LLM)
    participant H as Herramientas
    participant DB as PostgreSQL

    P->>S: "Necesito médico general, de mañanita"
    S->>H: buscar_cupos(especialidad)
    H->>DB: Disponibilidad única
    DB-->>S: Cupos libres
    S->>P: Ofrece 3 horarios de la mañana
    P->>S: "Sí, el martes a las 9"
    S->>H: agendar_cita(medico, inicio)
    H->>DB: INSERT (las reglas anti-cruce aplican)
    alt Cupo libre
        DB-->>S: Agendada
        S->>P: Confirmación en lenguaje simple
    else Alguien lo tomó primero
        DB-->>S: Rechazo con el motivo
        S->>P: Lo explica y propone otro horario
    end
```

### 3. Estados de una cita

```mermaid
stateDiagram-v2
    [*] --> programada: agendada
    [*] --> ofrecida: cupo de lista de espera
    ofrecida --> confirmada: acepta
    ofrecida --> cancelada: rechaza o vence
    programada --> confirmada: confirma
    programada --> cancelada: cancela con motivo
    programada --> atendida
    programada --> no_asistio
    confirmada --> cancelada: cancela con motivo
    confirmada --> atendida
    confirmada --> no_asistio
    cancelada --> [*]
    atendida --> [*]
    no_asistio --> [*]
```

Solo `ofrecida`, `programada` y `confirmada` ocupan el cupo.

---

## Base de Datos

Las reglas que evitan inconsistencias viven en el esquema, no solo en el código:

```sql
-- Un médico no puede tener dos citas activas que se crucen.
-- La base de datos lo garantiza incluso con reservas simultáneas.
CONSTRAINT medico_sin_traslape EXCLUDE USING gist
    (medico_id WITH =, tstzrange(inicio, fin, '[)') WITH &&)
    WHERE (estado IN ('ofrecida','programada','confirmada')),

-- Igual para la sala y para el paciente
CONSTRAINT sala_sin_traslape     EXCLUDE USING gist (...),
CONSTRAINT paciente_sin_traslape EXCLUDE USING gist (...),

-- La sala debe pertenecer a la sede de la cita
CONSTRAINT sala_del_centro FOREIGN KEY (sala_id, centro_id) REFERENCES salas(id, centro_id),

-- Cancelar exige motivo
CONSTRAINT cancelar_con_motivo CHECK (estado <> 'cancelada' OR motivo_cancelacion IS NOT NULL)
```

| Tabla | Propósito |
|---|---|
| `centros`, `salas`, `medicos`, `pacientes` | Catálogos, con borrado lógico |
| `citas` | Las citas, con las restricciones anti-cruce |
| `citas_historial` | Cada cambio de estado: nada se borra, todo se explica |
| `lista_espera` | La fila por especialidad, médico o sede |
| `notificaciones` | Trazabilidad de todo lo enviado |

---

## Instalación y Configuración

### Prerrequisitos

- Docker (Docker Desktop u OrbStack)
- Llave de Anthropic (opcional, solo para el asistente)

### 1. Clonar el repositorio

```bash
git clone https://github.com/lauramal/agendamiento-citas.git
cd agendamiento-citas
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Las reglas de negocio también se configuran ahí, sin tocar código:

```bash
DURACION_CITA_MIN=30           # duración por defecto de una cita
HORAS_RECORDATORIO=24          # anticipación del recordatorio
MINUTOS_RESERVA_OFERTA=120     # cuánto se guarda un cupo ofrecido
HORAS_MINIMAS_CANCELACION=2    # anticipación mínima para cancelar
```

### 3. Levantar todo

```bash
docker compose up --build
```

| Qué | Dónde |
|---|---|
| Documentación interactiva de la API | http://localhost:8000/docs |
| Página del paciente con el asistente | http://localhost:8000 |
| Correos enviados | http://localhost:8025 |

Se cargan datos de demostración: 2 sedes, 5 consultorios, 5 médicos, 4 pacientes y una agenda de cardiología casi llena.

### 4. Probar el flujo de la lista de espera

1. En `/docs`, `POST /citas/1/cancelar` con `{"motivo": "Viaje"}`.
2. En http://localhost:8025 aparece el correo a Gloria: "Se liberó una cita para usted".
3. Toque "Tomar esta cita" y la cita queda suya.

---

## Configuración Avanzada

### Asistente Nora

Agregue la llave en `.env` y entre a http://localhost:8000 con el documento `41000111` (Rosa, atención asistida) o `1020304050` (Daniel):

```bash
ANTHROPIC_API_KEY=su_llave
LLM_MODELO=anthropic:claude-haiku-4-5   # intercambiable, ej. openai:gpt-4o-mini
```

Sin llave, todo lo demás funciona.

### Correos a un Gmail real

Gmail exige una contraseña de aplicación (Cuenta de Google → Seguridad → Verificación en dos pasos → Contraseñas de aplicaciones):

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USUARIO=su.correo@gmail.com
SMTP_CLAVE=contraseña_de_aplicacion
SMTP_REMITENTE=su.correo@gmail.com
CORREO_REDIRIGIR_A=su.correo@gmail.com   # demo: todos los correos llegan aquí
```

---

## Decisiones de Diseño

Lo más importante de este proyecto es por qué está hecho así. El detalle completo, con contexto y consecuencias, está en [docs/decisiones.md](docs/decisiones.md).

| # | Decisión | Alternativa descartada | Por qué |
|---|---|---|---|
| D1 | Evitar cruces con restricciones de exclusión en PostgreSQL | Validar solo en el código | La validación en código tiene condición de carrera: dos reservas simultáneas pasan y ambas se guardan |
| D2 | PostgreSQL con Docker | Supabase en la nube / SQLite | Supabase es PostgreSQL y el esquema funciona igual allá, pero exigiría credenciales para evaluar. SQLite no soporta restricciones de exclusión |
| D3 | Python + FastAPI | Node/NestJS, Java/Spring | Productividad, validación con Pydantic y documentación interactiva automática |
| D4 | Una sola fuente de disponibilidad | Inventario por canal | Es la causa de fondo de que un canal "tenga más citas" que otro |
| D5 | Lista de espera con reserva temporal | Avisar a todos y que gane el más rápido | Avisar a todos premia al más conectado, lo contrario de lo que se busca |
| D6 | Eliminar = desactivar | Borrado físico | En salud el historial no se borra |
| D7 | El enlace del correo abre una página y el botón ejecuta | El enlace ejecuta la acción | Los antivirus del correo abren los enlaces; un enlace que cancela cancelaría citas solo |
| D8 | Agente con herramientas sobre los mismos servicios | Chatbot de flujos fijos / LLM con acceso a la base | El modelo no puede crear inconsistencias ni tocar citas ajenas: lo impide el diseño, no el prompt |
| D9 | WhatsApp y llamada detrás de la misma interfaz | Integrar WhatsApp ya | Su API exige aprobación de Meta; integrarlo es escribir un adaptador |
| D10 | Tareas dentro del proceso (APScheduler) | Worker aparte | Suficiente para el alcance; lo primero que cambiaría al escalar |
| D11 | Reglas de negocio configurables | Valores en el código | Cambiar una política de la institución no requiere desplegar |

---

## Seguridad

- **Reglas en la base de datos**: ningún canal puede saltarse las validaciones, ni con acceso directo.
- **Enlaces firmados**: cada enlace del correo lleva la cita y la acción firmadas con un secreto del servidor, y caduca.
- **Identidad por contexto en el agente**: el paciente viaja en el contexto de ejecución, no como parámetro del modelo. Nora no puede consultar ni cancelar citas de otra persona.
- **Sin datos sensibles en el repositorio**: `.env` está en `.gitignore`.

---

## Pruebas

```bash
pip install -r requirements.txt
docker compose up -d db
docker compose exec db createdb -U postgres citas_test
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/citas_test pytest
```

| Área | Qué se prueba |
|---|---|
| Cruces | Médico, sala y paciente; citas contiguas permitidas |
| Concurrencia | Tres reservas simultáneas del mismo cupo: solo una gana |
| Validaciones | Sala de otra sede, horario de la sede, citas en el pasado |
| Estados | Transiciones permitidas, reprogramación, historial |
| Lista de espera | Ofrecer, aceptar, rechazar conservando el turno, vencer |
| Correo | El enlace no actúa al abrirse; enlaces alterados rechazados |
| Agente | No toca citas ajenas; recibe el motivo cuando la base rechaza |
| Notificaciones | Recordatorios sin duplicados, respaldo de canal, modo demostración |

---

## Skills del Proyecto

Las tareas que se repiten en este repositorio están escritas como skills en `.claude/skills/`. Un skill es una carpeta con instrucciones que el agente carga solo cuando la tarea las necesita, en lugar de tenerlas siempre en el contexto.

| Skill | Cuándo se usa | Por qué existe |
|---|---|---|
| `nueva-regla-de-negocio` | Al agregar una validación o restricción | Una regla toca cuatro lugares: esquema, mensaje de error, servicio y pruebas. Es fácil olvidar uno. El skill fija el orden y la regla de que lo que pueda vivir en la base de datos no se valide solo en el código. Incluye las trampas que ya aparecieron al construir el proyecto |
| `registrar-decision` | Al tomar o documentar una decisión de diseño | Mantiene `docs/decisiones.md` con un solo formato y obliga a registrar la alternativa descartada, que es lo que da valor a cada decisión |

---

## Qué haría con más tiempo

- **Agenda del médico por sede**: turnos de qué días y en qué sede atiende cada médico.
- **Autenticación por rol** (paciente, recepción, administración) y verificación por código antes de hablar con el asistente.
- **WhatsApp real** como un adaptador más, con notas de voz transcritas.
- **Métricas de gestión**: inasistencia, cupos recuperados y tiempo hasta la primera cita disponible.
- **Evaluaciones del asistente**: conversaciones de prueba con resultados esperados en cada cambio del prompt o del modelo.
- **Migraciones versionadas** con Alembic.

---

## Licencia

Este proyecto está bajo la Licencia MIT. Ver `LICENSE` para más detalles.
