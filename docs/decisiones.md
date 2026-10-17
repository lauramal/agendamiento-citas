# Registro de decisiones

Cada decisión sigue el mismo formato: el contexto, las opciones que evalué, la que tomé, por qué, y lo que implica.

---

## D1. Cómo evitar citas cruzadas

**Contexto.** La regla más importante del sistema: un médico, una sala o un paciente no pueden tener dos citas que se crucen. El riesgo real no es el caso simple, es la concurrencia: dos personas pidiendo el mismo cupo al mismo instante desde canales distintos.

**Opciones.**
1. Validar en el código: consultar si hay cruce y, si no, guardar.
2. Bloquear filas (`SELECT ... FOR UPDATE`) antes de validar.
3. Restricciones de exclusión de PostgreSQL (`EXCLUDE USING gist` sobre rangos de tiempo).

**Decisión.** La 3, complementada con validación en el código para dar mensajes claros.

**Por qué.** La opción 1 tiene condición de carrera: las dos peticiones consultan, ninguna ve cruce y ambas guardan. La 2 funciona, pero depende de que cada desarrollador recuerde bloquear y no protege si alguien escribe en la base por otra vía. La 3 hace que la base de datos rechace el cruce de forma atómica, sin importar el canal ni quién escriba. La prueba `test_dos_reservas_simultaneas_solo_una_gana` lanza tres reservas en paralelo y verifica que solo una gana.

**Implica.** Requiere PostgreSQL (y la extensión `btree_gist`). Los errores de la base se traducen a mensajes entendibles en `app/errores.py`. Las restricciones solo consideran estados que ocupan el cupo (`ofrecida`, `programada`, `confirmada`): una cita cancelada libera el horario.

---

## D2. Base de datos y forma de entregarla

**Opciones.** Supabase en la nube · PostgreSQL local con Docker · SQLite.

**Decisión.** PostgreSQL 16 con Docker Compose.

**Por qué.** Supabase es PostgreSQL, así que el esquema funciona igual allá y sería mi opción para producción por lo que agrega (autenticación, almacenamiento, panel). Pero para evaluar exigiría compartir credenciales o que el evaluador cree una cuenta. Con Docker se levanta todo con un comando. SQLite se descartó porque no soporta restricciones de exclusión, y la regla central quedaría solo en el código (ver D1).

---

## D3. Lenguaje y framework

**Opciones.** Python + FastAPI · Node + NestJS · Java + Spring Boot.

**Decisión.** Python + FastAPI.

**Por qué.** Es el stack en el que soy más productivo, Pydantic resuelve la validación de entrada de forma declarativa, y FastAPI genera documentación interactiva (`/docs`) donde el evaluador puede probar cada endpoint sin herramientas adicionales. Además, el ecosistema de agentes (LangChain, LangGraph) es nativo de Python. Spring habría sido igual de válido pero más ceremonioso para este alcance.

---

## D4. Una sola fuente de disponibilidad

**Contexto.** En muchas instituciones cada canal (web, WhatsApp, call center) maneja su propio inventario de cupos.

**Decisión.** Un único servicio de disponibilidad (`app/services/disponibilidad.py`) y un único servicio de agendamiento. La API REST, el asistente y los enlaces del correo los usan todos.

**Por qué.** Es la causa de fondo de que un canal "tenga más citas" que otro. Con una sola fuente, abrir un canal nuevo es conectarlo, no repartirle cupos.

---

## D5. Lista de espera

**Opciones.**
1. No tener lista de espera: el cupo liberado queda libre y lo toma quien lo vea primero.
2. Avisar a todos los interesados a la vez y que gane el más rápido.
3. Fila ordenada: ofrecer al primero que encaje, reservarle el cupo un tiempo corto y pasar al siguiente si no responde.

**Decisión.** La 3.

**Por qué.** La 1 desperdicia cupos o los deja a quien revisa la app constantemente. La 2 parece eficiente pero premia a quien está más conectado, que es justo lo contrario de lo que buscamos para adultos mayores. La 3 es justa y predecible.

**Implica.** La oferta se modela como una cita en estado `ofrecida` con fecha de vencimiento. Como ocupa el cupo, ningún otro canal puede tomarlo mientras la persona decide (las mismas restricciones de D1 lo garantizan). Si rechaza un horario, conserva su lugar en la fila; si deja vencer la oferta, sale. La reserva dura lo configurado (2 horas), pero nunca más allá de 30 minutos antes de la cita, y no se ofrecen cupos que empiezan en menos de 45 minutos.

---

## D6. Eliminar registros

**Opciones.** Borrado físico · borrado lógico (desactivar).

**Decisión.** Desactivar, y bloquearlo si hay citas próximas.

**Por qué.** En salud el historial de atención no se borra. Un médico que se retira no puede hacer desaparecer las citas que atendió. Bloquear la desactivación con citas próximas evita dejar pacientes con citas huérfanas.

---

## D7. Acciones desde el correo

**Contexto.** El recordatorio permite confirmar o cancelar sin iniciar sesión.

**Opciones.** El enlace ejecuta la acción directamente · el enlace abre una página y un botón ejecuta.

**Decisión.** La segunda, con enlaces firmados que caducan.

**Por qué.** Los filtros antivirus y antispam de los correos abren los enlaces para revisarlos. Si abrir el enlace cancelara, se cancelarían citas sin que el paciente hiciera nada. La firma (`itsdangerous`) impide fabricar un enlace para otra cita. La página tiene un solo botón grande y texto simple.

---

## D8. El asistente (Nora)

**Opciones.**
1. Chatbot de flujos fijos (estilo Dialogflow con intenciones).
2. Agente con un LLM que genera SQL o escribe en la base.
3. Agente con un LLM que usa herramientas que llaman a los servicios de negocio.

**Decisión.** La 3, con LangChain (`create_agent`, patrón ReAct sobre un grafo de LangGraph) y memoria por conversación con el checkpointer de LangGraph.

**Por qué.** La 1 se rompe en cuanto la persona escribe distinto a lo esperado, que es justo lo que pasa con adultos mayores. La 2 entrega al modelo un poder que no debe tener. La 3 combina conversación natural con las mismas garantías que cualquier canal: si el modelo intenta una cita cruzada, la base de datos la rechaza y el agente recibe el motivo para explicárselo al paciente.

**Límites del agente, por diseño y no por instrucción:**
- La identidad del paciente viaja en el contexto de ejecución (`ToolRuntime`), no como parámetro que el modelo elige. El modelo no puede consultar ni cancelar citas de otra persona. Probado en `tests/test_agente.py`.
- No hay herramienta para cambiar estados administrativos (atendida, inasistencia) ni para tocar catálogos.
- Pedir un "sí" explícito antes de agendar o cancelar está en las instrucciones. Para acciones irreversibles de mayor riesgo usaría una pausa de aprobación humana del grafo (interrupt de LangGraph); aquí no lo consideré necesario porque agendar y cancelar son reversibles.

**Personalidad.** Trato de usted, frases cortas, una pregunta a la vez, máximo tres opciones de horario en lenguaje natural, nunca códigos ni ids, y siempre la lista de espera como alternativa cuando no hay cupo. Si el paciente pidió atención asistida, el tono se simplifica más y se ofrece la llamada de una persona.

**Proveedor.** El modelo se configura con `LLM_MODELO` mediante `init_chat_model`; cambiar de proveedor es cambiar una variable.

---

## D9. Canales de notificación y accesibilidad

**Decisión.** Cada paciente tiene canal preferido (correo, WhatsApp, llamada) y un indicador de atención asistida. El correo se envía de verdad (Mailpit en local); WhatsApp y llamada implementan la misma interfaz y quedan simulados. Si el canal preferido no es correo, el correo se envía como respaldo.

**Por qué.** La accesibilidad no es solo letra grande: es no obligar a nadie a usar una app. La API oficial de WhatsApp requiere una cuenta empresarial aprobada por Meta, inviable para esta entrega; con la interfaz común, integrarla es escribir un adaptador. La página del paciente usa la tipografía Atkinson Hyperlegible (diseñada para baja visión), texto de 19 px, control de tamaño de letra, botones grandes y foco visible.

---

## D10. Tareas automáticas

**Opciones.** Dentro del proceso (APScheduler) · worker aparte (Celery + Redis) · programador externo (cron, Cloud Scheduler).

**Decisión.** APScheduler dentro del proceso: recordatorios cada 5 minutos y vencimiento de ofertas cada minuto.

**Por qué.** Suficiente para el alcance y sin infraestructura extra. Con más de una instancia de la API habría que moverlo a un programador externo para no duplicar envíos; es lo primero que cambiaría al escalar. Las tareas son idempotentes (marcan `recordatorio_enviado_en`), lo que facilita ese cambio.

---

## D11. Reglas de negocio configurables

Duración de la cita, anticipación del recordatorio, tiempo de reserva de una oferta y anticipación mínima para cancelar son variables de entorno, no números escritos en el código. Cambiar una política de la institución no requiere desplegar.
