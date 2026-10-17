"""Lista de espera con reasignación automática de cupos.

Flujo:
1. El paciente no encuentra cupo y se une a la lista (especialidad + rango de fechas,
   opcionalmente un médico o un centro).
2. Alguien cancela -> el cupo liberado se le ofrece al primero de la fila que encaje.
   Se crea una cita en estado 'ofrecida' que BLOQUEA el cupo por un tiempo corto
   (nadie más lo puede tomar mientras decide).
3. El paciente acepta (cita confirmada) o rechaza / deja vencer la oferta
   (el cupo pasa al siguiente de la fila).
"""
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.errores import ErrorNegocio, NoEncontrado
from app.models import Cita, ListaEspera, Medico, Paciente
from app.schemas import CitaCrear, EsperaCrear
from app.services import citas as svc_citas
from app.services.citas import ahora


def unirse(db: Session, datos: EsperaCrear) -> ListaEspera:
    if not db.get(Paciente, datos.paciente_id):
        raise NoEncontrado("El paciente")
    if datos.desde < ahora().date():
        raise ErrorNegocio("El rango de la lista de espera debe ser desde hoy en adelante.")
    duplicada = db.scalar(select(ListaEspera).where(
        ListaEspera.paciente_id == datos.paciente_id,
        ListaEspera.especialidad.ilike(datos.especialidad),
        ListaEspera.estado.in_(("esperando", "ofrecida"))))
    if duplicada:
        raise ErrorNegocio("El paciente ya está en lista de espera para esa especialidad.", 409)
    entrada = ListaEspera(**datos.model_dump())
    db.add(entrada)
    db.commit()
    return entrada


def retirar(db: Session, espera_id: int) -> ListaEspera:
    entrada = db.get(ListaEspera, espera_id)
    if not entrada:
        raise NoEncontrado("La solicitud de lista de espera")
    if entrada.estado not in ("esperando",):
        raise ErrorNegocio(f"La solicitud está '{entrada.estado}' y no se puede retirar.")
    entrada.estado = "retirada"
    db.commit()
    return entrada


def ofrecer_cupo_liberado(db: Session, cita_liberada: Cita,
                          excluir_pacientes: set[int] | None = None) -> ListaEspera | None:
    """Ofrece el cupo de una cita cancelada al primero de la fila que encaje."""
    if cita_liberada.inicio - ahora() < timedelta(minutes=45):
        return None   # demasiado cerca: nadie alcanza a llegar
    excluir = set(excluir_pacientes or set()) | {cita_liberada.paciente_id}
    medico = db.get(Medico, cita_liberada.medico_id)
    fecha = cita_liberada.inicio.astimezone(settings.tz).date()

    candidatos = db.scalars(
        select(ListaEspera).where(
            ListaEspera.estado == "esperando",
            ListaEspera.especialidad.ilike(medico.especialidad),
            or_(ListaEspera.medico_id.is_(None), ListaEspera.medico_id == medico.id),
            or_(ListaEspera.centro_id.is_(None), ListaEspera.centro_id == cita_liberada.centro_id),
            ListaEspera.desde <= fecha,
            ListaEspera.hasta >= fecha,
            ListaEspera.paciente_id.not_in(excluir),
        ).order_by(ListaEspera.creado_en, ListaEspera.id)
    ).all()

    # La reserva dura lo configurado, pero nunca más allá de 30 min antes de la cita
    expira = min(ahora() + timedelta(minutes=settings.minutos_reserva_oferta),
                 cita_liberada.inicio - timedelta(minutes=30))

    for entrada in candidatos:
        try:
            oferta = svc_citas.crear_cita(db, CitaCrear(
                paciente_id=entrada.paciente_id, medico_id=cita_liberada.medico_id,
                centro_id=cita_liberada.centro_id, sala_id=cita_liberada.sala_id,
                inicio=cita_liberada.inicio, duracion_min=cita_liberada.duracion_min,
                motivo_consulta="Cupo liberado (lista de espera)",
            ), estado="ofrecida", oferta_expira_en=expira, notificar=False)
        except (ErrorNegocio, IntegrityError):
            db.rollback()
            continue   # ej. el paciente ya tiene otra cita a esa hora: pasa al siguiente
        entrada.estado = "ofrecida"
        entrada.cita_ofrecida_id = oferta.id
        db.commit()
        from app.services import notificaciones
        notificaciones.oferta_cupo(db, oferta)
        return entrada
    return None


def _entrada_de_oferta(db: Session, cita: Cita) -> ListaEspera:
    entrada = db.scalar(select(ListaEspera).where(ListaEspera.cita_ofrecida_id == cita.id))
    if not entrada:
        raise NoEncontrado("La oferta")
    return entrada


def aceptar_oferta(db: Session, cita_id: int, canal: str = "api") -> Cita:
    cita = svc_citas.obtener_cita(db, cita_id)
    if cita.estado != "ofrecida":
        raise ErrorNegocio("Esta oferta ya no está disponible.")
    if cita.oferta_expira_en and cita.oferta_expira_en < ahora():
        raise ErrorNegocio("La oferta venció y el cupo pasó a otra persona.")
    entrada = _entrada_de_oferta(db, cita)
    svc_citas.cambiar_estado(db, cita.id, "confirmada", canal, "Oferta de lista de espera aceptada")
    entrada.estado = "asignada"
    db.commit()
    return cita


def _liberar_oferta(db: Session, cita: Cita, motivo: str, nuevo_estado_espera: str,
                    canal: str) -> None:
    entrada = _entrada_de_oferta(db, cita)
    anterior = cita.estado
    cita.estado = "cancelada"
    cita.motivo_cancelacion = motivo
    cita.actualizado_en = ahora()
    svc_citas.registrar_historial(db, cita, anterior, "cancelada", motivo, canal)
    entrada.estado = nuevo_estado_espera
    entrada.cita_ofrecida_id = None if nuevo_estado_espera == "esperando" else entrada.cita_ofrecida_id
    db.commit()
    # el cupo pasa al siguiente de la fila
    ofrecer_cupo_liberado(db, cita, excluir_pacientes={entrada.paciente_id})


def rechazar_oferta(db: Session, cita_id: int, canal: str = "api") -> None:
    cita = svc_citas.obtener_cita(db, cita_id)
    if cita.estado != "ofrecida":
        raise ErrorNegocio("Esta oferta ya no está disponible.")
    # Rechazar un horario no saca al paciente de la fila: conserva su turno
    _liberar_oferta(db, cita, "Oferta rechazada por el paciente", "esperando", canal)


def expirar_ofertas(db: Session, momento: datetime | None = None) -> int:
    momento = momento or ahora()
    vencidas = db.scalars(select(Cita).where(
        Cita.estado == "ofrecida", Cita.oferta_expira_en < momento)).all()
    for cita in vencidas:
        _liberar_oferta(db, cita, "Oferta vencida sin respuesta", "expirada", "sistema")
    return len(vencidas)
