"""Disponibilidad: la ÚNICA fuente de verdad de cupos.

El problema de fondo que ataca esta solución: en muchas instituciones cada
canal (web, WhatsApp, call center) maneja su propio inventario de citas,
por eso un canal "tiene más citas" que otro. Aquí todos los canales —
incluido el agente— consultan esta misma función. Si un cupo existe,
existe para todos.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Centro, Cita, Medico, Sala
from app.schemas import Cupo
from app.services.citas import ESTADOS_ACTIVOS, ahora


def _choca(inicio: datetime, fin: datetime, ocupados: list[tuple[datetime, datetime]]) -> bool:
    return any(inicio < f and fin > i for i, f in ocupados)


def cupos(db: Session, fecha: date, *, especialidad: str | None = None,
          medico_id: int | None = None, centro_id: int | None = None,
          duracion_min: int | None = None, limite: int = 30) -> list[Cupo]:
    duracion = timedelta(minutes=duracion_min or settings.duracion_cita_min)
    margen = ahora() + timedelta(minutes=30)   # no ofrecer cupos que empiezan ya

    q_medicos = select(Medico).where(Medico.activo.is_(True))
    if medico_id:
        q_medicos = q_medicos.where(Medico.id == medico_id)
    if especialidad:
        q_medicos = q_medicos.where(Medico.especialidad.ilike(especialidad))
    medicos = list(db.scalars(q_medicos.order_by(Medico.id)))

    q_centros = select(Centro).where(Centro.activo.is_(True))
    if centro_id:
        q_centros = q_centros.where(Centro.id == centro_id)
    centros = list(db.scalars(q_centros.order_by(Centro.id)))
    if not medicos or not centros:
        return []

    dia_ini = datetime.combine(fecha, datetime.min.time(), tzinfo=settings.tz)
    dia_fin = dia_ini + timedelta(days=1)
    # Una sola consulta con todas las citas activas del día
    activas = list(db.scalars(select(Cita).where(
        Cita.estado.in_(ESTADOS_ACTIVOS), Cita.inicio < dia_fin, Cita.fin > dia_ini)))
    ocupacion_medico: dict[int, list] = {}
    ocupacion_sala: dict[int, list] = {}
    for c in activas:
        ocupacion_medico.setdefault(c.medico_id, []).append((c.inicio, c.fin))
        ocupacion_sala.setdefault(c.sala_id, []).append((c.inicio, c.fin))

    salas_por_centro: dict[int, list[Sala]] = {}
    for s in db.scalars(select(Sala).where(Sala.activo.is_(True)).order_by(Sala.id)):
        salas_por_centro.setdefault(s.centro_id, []).append(s)

    resultado: list[Cupo] = []
    for centro in centros:
        salas = salas_por_centro.get(centro.id, [])
        if not salas:
            continue
        inicio = datetime.combine(fecha, centro.hora_apertura, tzinfo=settings.tz)
        cierre = datetime.combine(fecha, centro.hora_cierre, tzinfo=settings.tz)
        while inicio + duracion <= cierre:
            fin = inicio + duracion
            if inicio >= margen:
                sala = next((s for s in salas
                             if not _choca(inicio, fin, ocupacion_sala.get(s.id, []))), None)
                if sala:
                    for m in medicos:
                        if not _choca(inicio, fin, ocupacion_medico.get(m.id, [])):
                            resultado.append(Cupo(
                                medico_id=m.id, medico=m.nombre_completo, especialidad=m.especialidad,
                                centro_id=centro.id, centro=centro.nombre,
                                sala_id=sala.id, sala=sala.nombre, inicio=inicio, fin=fin))
                            if len(resultado) >= limite:
                                return resultado
            inicio = fin
    return resultado


def proximos_cupos(db: Session, *, especialidad: str | None = None, medico_id: int | None = None,
                   centro_id: int | None = None, dias: int = 14, limite: int = 5) -> list[Cupo]:
    """Los primeros cupos disponibles en los próximos días (lo que más pide la gente)."""
    hoy = ahora().date()
    encontrados: list[Cupo] = []
    for d in range(dias):
        encontrados += cupos(db, hoy + timedelta(days=d), especialidad=especialidad,
                             medico_id=medico_id, centro_id=centro_id, limite=limite)
        if len(encontrados) >= limite:
            break
    return encontrados[:limite]
