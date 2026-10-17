"""Nora: asistente conversacional de citas (LangChain + LangGraph).

Arquitectura:
- Patrón ReAct (razonar -> usar herramienta -> observar -> responder) con
  `create_agent` de LangChain, que corre sobre un grafo de LangGraph.
- Las herramientas llaman a los MISMOS servicios que la API REST. El agente
  nunca escribe en la base de datos por su cuenta: si intenta algo inválido
  (una cita cruzada, cancelar fuera de plazo), la regla de negocio o la base
  de datos lo rechazan y el agente recibe el motivo para explicarlo.
- Identidad por contexto, no por el modelo: el paciente se identifica antes
  de hablar con el agente y su id viaja en el contexto de ejecución
  (ToolRuntime). El LLM no puede elegir de quién son las citas que consulta
  o cancela.
- Memoria por conversación con el checkpointer de LangGraph.
"""
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.errores import ErrorNegocio
from app.models import Centro, Cita, Medico, Paciente
from app.schemas import CitaCrear, EsperaCrear
from app.services import citas as svc_citas
from app.services import disponibilidad, lista_espera
from app.services.citas import ahora
from app.services.notificaciones import DIAS, MESES, fecha_humana


@dataclass
class ContextoPaciente:
    paciente_id: int


def _humano(momento: datetime) -> str:
    f = momento.astimezone(settings.tz)
    hora = f.strftime("%I:%M %p").lstrip("0").replace("AM", "a. m.").replace("PM", "p. m.")
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month - 1]}, {hora}"


def _ok(datos) -> str:
    return json.dumps(datos, ensure_ascii=False, default=str)


def _error(e: ErrorNegocio) -> str:
    return _ok({"resultado": "no_permitido", "motivo": e.mensaje})


# ---------------- Herramientas ----------------
@tool
def ver_especialidades_y_centros() -> str:
    """Lista las especialidades disponibles y los centros de atención con su dirección y horario."""
    with SessionLocal() as db:
        esp = sorted({m.especialidad for m in db.scalars(select(Medico).where(Medico.activo.is_(True)))})
        centros = [{"centro_id": c.id, "nombre": c.nombre, "direccion": c.direccion,
                    "horario": f"{c.hora_apertura:%H:%M}-{c.hora_cierre:%H:%M}"}
                   for c in db.scalars(select(Centro).where(Centro.activo.is_(True)))]
    return _ok({"especialidades": esp, "centros": centros})


@tool
def buscar_cupos(especialidad: str, fecha: str | None = None, centro_id: int | None = None) -> str:
    """Busca citas disponibles para una especialidad.
    fecha: 'AAAA-MM-DD' para un día específico; si se omite, trae los primeros cupos de las próximas 2 semanas.
    centro_id: opcional, para limitar a un centro."""
    with SessionLocal() as db:
        if fecha:
            cupos = disponibilidad.cupos(db, date.fromisoformat(fecha), especialidad=especialidad,
                                         centro_id=centro_id, limite=6)
        else:
            cupos = disponibilidad.proximos_cupos(db, especialidad=especialidad,
                                                  centro_id=centro_id, limite=6)
    if not cupos:
        return _ok({"resultado": "sin_cupos",
                    "sugerencia": "Ofrecer unirse a la lista de espera para recibir aviso si se libera un turno."})
    return _ok({"cupos": [{"medico_id": c.medico_id, "medico": c.medico, "centro_id": c.centro_id,
                           "centro": c.centro, "inicio": c.inicio.isoformat(),
                           "cuando": _humano(c.inicio)}
                          for c in cupos]})


@tool
def mis_citas(runtime: ToolRuntime[ContextoPaciente]) -> str:
    """Muestra las próximas citas del paciente que está conversando (incluye ofertas de lista de espera)."""
    with SessionLocal() as db:
        citas = svc_citas.citas_de_paciente(db, runtime.context.paciente_id, solo_proximas=True)
        return _ok({"citas": [{"cita_id": c.id, "estado": c.estado, "cuando": fecha_humana(c),
                               "medico": c.medico.nombre_completo, "especialidad": c.medico.especialidad,
                               "centro": c.centro.nombre, "direccion": c.centro.direccion}
                              for c in citas]})


@tool
def agendar_cita(medico_id: int, centro_id: int, inicio: str, motivo: str | None,
                 runtime: ToolRuntime[ContextoPaciente]) -> str:
    """Agenda una cita para el paciente. Usar SOLO después de que el paciente confirmó explícitamente
    el médico, el centro y el horario. inicio: fecha y hora ISO tal como la devolvió buscar_cupos."""
    with SessionLocal() as db:
        try:
            c = svc_citas.crear_cita(db, CitaCrear(
                paciente_id=runtime.context.paciente_id, medico_id=medico_id, centro_id=centro_id,
                inicio=datetime.fromisoformat(inicio), motivo_consulta=motivo, canal_origen="agente"))
        except ErrorNegocio as e:
            return _error(e)
        return _ok({"resultado": "agendada", "cita_id": c.id, "cuando": fecha_humana(c),
                    "lugar": f"{c.centro.nombre}, {c.centro.direccion}",
                    "nota": "Se envió la confirmación por el canal preferido del paciente."})


@tool
def cancelar_cita(cita_id: int, motivo: str, runtime: ToolRuntime[ContextoPaciente]) -> str:
    """Cancela una cita del paciente. Usar SOLO después de que el paciente confirmó que quiere cancelarla."""
    with SessionLocal() as db:
        cita = db.get(Cita, cita_id)
        if not cita or cita.paciente_id != runtime.context.paciente_id:
            return _ok({"resultado": "no_permitido", "motivo": "Esa cita no pertenece a este paciente."})
        try:
            svc_citas.cancelar(db, cita_id, motivo, canal="agente")
        except ErrorNegocio as e:
            return _error(e)
    return _ok({"resultado": "cancelada", "nota": "El turno se ofreció a la lista de espera."})


@tool
def unirme_lista_espera(especialidad: str, runtime: ToolRuntime[ContextoPaciente],
                        dias: int = 14, centro_id: int | None = None) -> str:
    """Inscribe al paciente en la lista de espera de una especialidad por los próximos 'dias' días.
    Si alguien cancela, se le reserva el turno y se le avisa por su canal preferido."""
    hoy = ahora().date()
    with SessionLocal() as db:
        try:
            e = lista_espera.unirse(db, EsperaCrear(
                paciente_id=runtime.context.paciente_id, especialidad=especialidad,
                centro_id=centro_id, desde=hoy, hasta=hoy + timedelta(days=dias)))
        except ErrorNegocio as err:
            return _error(err)
    return _ok({"resultado": "en_lista_espera", "solicitud_id": e.id, "hasta": str(e.hasta)})


@tool
def responder_oferta(cita_id: int, acepta: bool, runtime: ToolRuntime[ContextoPaciente]) -> str:
    """Acepta o rechaza una cita ofrecida desde la lista de espera (estado 'ofrecida')."""
    with SessionLocal() as db:
        cita = db.get(Cita, cita_id)
        if not cita or cita.paciente_id != runtime.context.paciente_id:
            return _ok({"resultado": "no_permitido", "motivo": "Esa oferta no pertenece a este paciente."})
        try:
            if acepta:
                lista_espera.aceptar_oferta(db, cita_id, "agente")
                return _ok({"resultado": "confirmada"})
            lista_espera.rechazar_oferta(db, cita_id, "agente")
            return _ok({"resultado": "rechazada", "nota": "Sigue en la lista de espera."})
        except ErrorNegocio as e:
            return _error(e)


HERRAMIENTAS = [ver_especialidades_y_centros, buscar_cupos, mis_citas, agendar_cita,
                cancelar_cita, unirme_lista_espera, responder_oferta]


def _instrucciones(paciente: Paciente) -> str:
    hoy = ahora()
    estilo = ("Esta persona pidió atención asistida: use frases todavía más cortas, una sola pregunta "
              "a la vez, y ofrezca siempre la opción de que una persona la llame."
              if paciente.atencion_asistida else "")
    return f"""Usted es Nora, la asistente de citas del centro médico. Hoy es {_humano(hoy)} \
(hora de Bogotá). Está hablando con {paciente.nombres}.

Su forma de ser: cálida, paciente y clara, como una recepcionista amable que conoce a sus pacientes.
Muchas de las personas que le escriben son adultas mayores o no se sienten cómodas con la tecnología.
- Trate de "usted". Frases cortas. Nada de tecnicismos ni de códigos o ids en sus respuestas.
- Una sola pregunta por mensaje. Ofrezca máximo 3 opciones de horario a la vez, en lenguaje natural
  ("el martes 14 a las 9 de la mañana").
- Si no hay cupos, no termine ahí: ofrezca la lista de espera y explique que se le avisará si se libera un turno.
- Antes de agendar o cancelar, repita los datos y pida un "sí" explícito. Nunca agende ni cancele sin ese sí.
- Si una herramienta responde "no_permitido", explique el motivo con amabilidad y proponga una alternativa.
- No dé consejos médicos. Si la persona describe una urgencia, indíquele que llame a la línea de emergencias 123 \
o acuda a urgencias.
{estilo}"""


_memoria = InMemorySaver()


def conversar(paciente_id: int, mensaje: str, conversacion_id: str) -> str:
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    with SessionLocal() as db:
        paciente = db.get(Paciente, paciente_id)
        instrucciones = _instrucciones(paciente)
    agente = create_agent(
        model=init_chat_model(settings.llm_modelo, temperature=0.3),
        tools=HERRAMIENTAS,
        system_prompt=instrucciones,
        context_schema=ContextoPaciente,
        checkpointer=_memoria,
    )
    resultado = agente.invoke(
        {"messages": [{"role": "user", "content": mensaje}]},
        config={"configurable": {"thread_id": f"{paciente_id}:{conversacion_id}"}},
        context=ContextoPaciente(paciente_id=paciente_id),
    )
    return resultado["messages"][-1].content if isinstance(resultado["messages"][-1].content, str) \
        else "".join(b.get("text", "") for b in resultado["messages"][-1].content if isinstance(b, dict))
