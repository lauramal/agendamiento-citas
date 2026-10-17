from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CitaHistorial
from app.schemas import CitaCambioEstado, CitaCancelar, CitaCrear, CitaOut, CitaReprogramar, Cupo
from app.services import citas as svc
from app.services import disponibilidad

router = APIRouter(tags=["Citas"])


@router.get("/disponibilidad", response_model=list[Cupo],
            summary="Cupos libres (la misma fuente para todos los canales)")
def ver_disponibilidad(fecha: date, especialidad: str | None = None, medico_id: int | None = None,
                       centro_id: int | None = None, limite: int = Query(30, le=200),
                       db: Session = Depends(get_db)):
    return disponibilidad.cupos(db, fecha, especialidad=especialidad, medico_id=medico_id,
                                centro_id=centro_id, limite=limite)


@router.post("/citas", response_model=CitaOut, status_code=201)
def agendar(datos: CitaCrear, db: Session = Depends(get_db)):
    return svc.crear_cita(db, datos)


@router.get("/citas/{cita_id}", response_model=CitaOut)
def ver_cita(cita_id: int, db: Session = Depends(get_db)):
    return svc.obtener_cita(db, cita_id)


@router.get("/citas/{cita_id}/historial")
def historial(cita_id: int, db: Session = Depends(get_db)):
    svc.obtener_cita(db, cita_id)
    filas = db.scalars(select(CitaHistorial).where(CitaHistorial.cita_id == cita_id)
                       .order_by(CitaHistorial.id)).all()
    return [{"de": f.estado_anterior, "a": f.estado_nuevo, "detalle": f.detalle,
             "canal": f.canal, "fecha": f.creado_en} for f in filas]


@router.post("/citas/{cita_id}/cancelar", response_model=CitaOut)
def cancelar(cita_id: int, datos: CitaCancelar, db: Session = Depends(get_db)):
    return svc.cancelar(db, cita_id, datos.motivo)


@router.post("/citas/{cita_id}/reprogramar", response_model=CitaOut)
def reprogramar(cita_id: int, datos: CitaReprogramar, db: Session = Depends(get_db)):
    return svc.reprogramar(db, cita_id, datos.inicio)


@router.post("/citas/{cita_id}/estado", response_model=CitaOut)
def cambiar_estado(cita_id: int, datos: CitaCambioEstado, db: Session = Depends(get_db)):
    return svc.cambiar_estado(db, cita_id, datos.estado)


@router.get("/pacientes/{paciente_id}/citas", response_model=list[CitaOut], tags=["Pacientes"])
def citas_paciente(paciente_id: int, solo_proximas: bool = False, estado: str | None = None,
                   db: Session = Depends(get_db)):
    return svc.citas_de_paciente(db, paciente_id, solo_proximas, estado)


@router.get("/centros/{centro_id}/citas", response_model=list[CitaOut], tags=["Centros de atención"])
def citas_centro(centro_id: int, fecha: date | None = None, sala_id: int | None = None,
                 estado: str | None = None, db: Session = Depends(get_db)):
    return svc.citas_de_centro(db, centro_id, fecha, sala_id, estado)


@router.get("/salas/{sala_id}/citas", response_model=list[CitaOut], tags=["Salas"])
def citas_sala(sala_id: int, fecha: date | None = None, db: Session = Depends(get_db)):
    return svc.citas_de_sala(db, sala_id, fecha)
