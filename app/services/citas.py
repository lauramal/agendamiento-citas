"""Reglas de negocio de las citas.

Dos capas de validación:
1. Aquí, en el servicio: mensajes claros y reglas que dependen del contexto
   (horario del centro, transiciones de estado, anticipación para cancelar).
2. En la base de datos: lo que nunca puede romperse, ni con dos reservas
   simultáneas (traslapes de médico, sala y paciente; sala del centro).
"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.errores import ErrorNegocio, NoEncontrado, traducir_integridad
from app.models import Centro, Cita, CitaHistorial, Medico, Paciente, Sala
from app.schemas import CitaCrear

ESTADOS_ACTIVOS = ("ofrecida", "programada", "confirmada")

# Máquina de estados: qué cambios están permitidos
TRANSICIONES: dict[str, set[str]] = {
    "ofrecida": {"confirmada", "cancelada"},
    "programada": {"confirmada", "cancelada", "atendida", "no_asistio"},
    "confirmada": {"cancelada", "atendida", "no_asistio"},
    "cancelada": set(),
    "atendida": set(),
    "no_asistio": set(),
}


def ahora() -> datetime:
    return datetime.now(settings.tz)


def obtener_cita(db: Session, cita_id: int) -> Cita:
    cita = db.get(Cita, cita_id)
    if not cita:
        raise NoEncontrado("La cita")
    return cita


def registrar_historial(db: Session, cita: Cita, anterior: str | None, nuevo: str,
                        detalle: str | None = None, canal: str | None = None) -> None:
    db.add(CitaHistorial(cita_id=cita.id, estado_anterior=anterior, estado_nuevo=nuevo,
                         detalle=detalle, canal=canal))


def _validar_horario(centro: Centro, inicio: datetime, fin: datetime) -> None:
    ini_local = inicio.astimezone(settings.tz)
    fin_local = fin.astimezone(settings.tz)
    if ini_local.date() != fin_local.date():
        raise ErrorNegocio("La cita debe empezar y terminar el mismo día.")
    if ini_local.time() < centro.hora_apertura or fin_local.time() > centro.hora_cierre:
        raise ErrorNegocio(
            f"{centro.nombre} atiende de {centro.hora_apertura:%H:%M} a {centro.hora_cierre:%H:%M}."
        )


def sala_libre(db: Session, centro_id: int, inicio: datetime, fin: datetime) -> Sala | None:
    """Primera sala activa del centro sin citas activas que se crucen."""
    ocupadas = select(Cita.sala_id).where(
        Cita.centro_id == centro_id,
        Cita.estado.in_(ESTADOS_ACTIVOS),
        Cita.inicio < fin,
        Cita.fin > inicio,
    )
    return db.scalars(
        select(Sala)
        .where(Sala.centro_id == centro_id, Sala.activo.is_(True), Sala.id.not_in(ocupadas))
        .order_by(Sala.id)
    ).first()


def crear_cita(db: Session, datos: CitaCrear, *, estado: str = "programada",
               oferta_expira_en: datetime | None = None, notificar: bool = True) -> Cita:
    paciente = db.get(Paciente, datos.paciente_id)
    if not paciente or not paciente.activo:
        raise NoEncontrado("El paciente")
    medico = db.get(Medico, datos.medico_id)
    if not medico or not medico.activo:
        raise NoEncontrado("El médico")
    centro = db.get(Centro, datos.centro_id)
    if not centro or not centro.activo:
        raise NoEncontrado("El centro de atención")

    inicio = datos.inicio if datos.inicio.tzinfo else datos.inicio.replace(tzinfo=settings.tz)
    duracion = datos.duracion_min or settings.duracion_cita_min
    fin = inicio + timedelta(minutes=duracion)

    if inicio <= ahora():
        raise ErrorNegocio("No se pueden agendar citas en el pasado.")
    _validar_horario(centro, inicio, fin)

    if datos.sala_id is not None:
        sala = db.get(Sala, datos.sala_id)
        if not sala or not sala.activo:
            raise NoEncontrado("La sala")
    else:
        sala = sala_libre(db, centro.id, inicio, fin)
        if not sala:
            raise ErrorNegocio("No hay salas libres en ese centro a esa hora.", 409)

    cita = Cita(paciente_id=paciente.id, medico_id=medico.id, centro_id=centro.id,
                sala_id=sala.id, inicio=inicio, fin=fin, duracion_min=duracion,
                estado=estado, motivo_consulta=datos.motivo_consulta,
                canal_origen="lista_espera" if estado == "ofrecida" else datos.canal_origen,
                oferta_expira_en=oferta_expira_en)
    db.add(cita)
    try:
        db.flush()   # aquí la base de datos aplica las restricciones anti-traslape
    except IntegrityError as e:
        db.rollback()
        raise traducir_integridad(e) from e
    registrar_historial(db, cita, None, estado, "Cita creada", cita.canal_origen)
    db.commit()

    if notificar and estado == "programada":
        from app.services import notificaciones
        notificaciones.confirmacion_agendamiento(db, cita)
    return cita


def reprogramar(db: Session, cita_id: int, nuevo_inicio: datetime, canal: str = "api") -> Cita:
    cita = obtener_cita(db, cita_id)
    if cita.estado not in ("programada", "confirmada"):
        raise ErrorNegocio(f"Una cita en estado '{cita.estado}' no se puede reprogramar.")
    inicio = nuevo_inicio if nuevo_inicio.tzinfo else nuevo_inicio.replace(tzinfo=settings.tz)
    if inicio <= ahora():
        raise ErrorNegocio("No se puede reprogramar al pasado.")
    fin = inicio + timedelta(minutes=cita.duracion_min)
    _validar_horario(cita.centro, inicio, fin)

    anterior_inicio, estado_previo = cita.inicio, cita.estado
    sala = sala_libre(db, cita.centro_id, inicio, fin)
    if not sala:
        raise ErrorNegocio("No hay salas libres en ese centro a esa hora.", 409)
    cita.inicio, cita.fin, cita.sala_id = inicio, fin, sala.id
    cita.estado = "programada"   # un horario nuevo requiere confirmarse de nuevo
    cita.recordatorio_enviado_en = None
    cita.actualizado_en = ahora()
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise traducir_integridad(e) from e
    registrar_historial(db, cita, estado_previo, "programada",
                        f"Reprogramada desde {anterior_inicio.astimezone(settings.tz):%Y-%m-%d %H:%M}", canal)
    db.commit()
    return cita


def cambiar_estado(db: Session, cita_id: int, nuevo: str, canal: str = "api",
                   detalle: str | None = None) -> Cita:
    cita = obtener_cita(db, cita_id)
    if nuevo not in TRANSICIONES[cita.estado]:
        raise ErrorNegocio(f"No se puede pasar de '{cita.estado}' a '{nuevo}'.")
    if nuevo in ("atendida", "no_asistio") and cita.inicio > ahora():
        raise ErrorNegocio("Solo se puede marcar atendida o inasistencia cuando la cita ya empezó.")
    anterior = cita.estado
    cita.estado = nuevo
    cita.actualizado_en = ahora()
    registrar_historial(db, cita, anterior, nuevo, detalle, canal)
    db.commit()
    return cita


def cancelar(db: Session, cita_id: int, motivo: str, canal: str = "api",
             reofrecer: bool = True) -> Cita:
    cita = obtener_cita(db, cita_id)
    if cita.estado not in ("programada", "confirmada"):
        raise ErrorNegocio(f"Una cita en estado '{cita.estado}' no se puede cancelar.")
    if cita.inicio - ahora() < timedelta(hours=settings.horas_minimas_cancelacion):
        raise ErrorNegocio(
            f"Las citas se cancelan con al menos {settings.horas_minimas_cancelacion} horas de anticipación. "
            "Comuníquese con el centro de atención."
        )
    anterior = cita.estado
    cita.estado = "cancelada"
    cita.motivo_cancelacion = motivo
    cita.actualizado_en = ahora()
    registrar_historial(db, cita, anterior, "cancelada", motivo, canal)
    db.commit()

    # El cupo liberado se ofrece de inmediato a la lista de espera
    if reofrecer:
        from app.services import lista_espera
        lista_espera.ofrecer_cupo_liberado(db, cita)
    return cita


# ---------- Consultas ----------
def _rango_dia(fecha: date) -> tuple[datetime, datetime]:
    inicio = datetime.combine(fecha, time.min, tzinfo=settings.tz)
    return inicio, inicio + timedelta(days=1)


def citas_de_paciente(db: Session, paciente_id: int, solo_proximas: bool = False,
                      estado: str | None = None) -> list[Cita]:
    if not db.get(Paciente, paciente_id):
        raise NoEncontrado("El paciente")
    q = select(Cita).where(Cita.paciente_id == paciente_id)
    if solo_proximas:
        q = q.where(Cita.inicio >= ahora(), Cita.estado.in_(ESTADOS_ACTIVOS))
    if estado:
        q = q.where(Cita.estado == estado)
    return list(db.scalars(q.order_by(Cita.inicio)))


def citas_de_centro(db: Session, centro_id: int, fecha: date | None = None,
                    sala_id: int | None = None, estado: str | None = None) -> list[Cita]:
    if not db.get(Centro, centro_id):
        raise NoEncontrado("El centro de atención")
    q = select(Cita).where(Cita.centro_id == centro_id)
    if fecha:
        desde, hasta = _rango_dia(fecha)
        q = q.where(Cita.inicio >= desde, Cita.inicio < hasta)
    if sala_id:
        q = q.where(Cita.sala_id == sala_id)
    if estado:
        q = q.where(Cita.estado == estado)
    return list(db.scalars(q.order_by(Cita.inicio)))


def citas_de_sala(db: Session, sala_id: int, fecha: date | None = None) -> list[Cita]:
    sala = db.get(Sala, sala_id)
    if not sala:
        raise NoEncontrado("La sala")
    return citas_de_centro(db, sala.centro_id, fecha=fecha, sala_id=sala_id)
