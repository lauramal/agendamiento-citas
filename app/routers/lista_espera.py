from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ListaEspera
from app.schemas import CitaOut, EsperaCrear, EsperaOut
from app.services import lista_espera as svc

router = APIRouter(prefix="/lista-espera", tags=["Lista de espera"])


@router.post("", response_model=EsperaOut, status_code=201)
def unirse(datos: EsperaCrear, db: Session = Depends(get_db)):
    return svc.unirse(db, datos)


@router.get("", response_model=list[EsperaOut])
def listar(estado: str | None = "esperando", especialidad: str | None = None,
           db: Session = Depends(get_db)):
    q = select(ListaEspera)
    if estado:
        q = q.where(ListaEspera.estado == estado)
    if especialidad:
        q = q.where(ListaEspera.especialidad.ilike(especialidad))
    return db.scalars(q.order_by(ListaEspera.creado_en)).all()


@router.delete("/{espera_id}", response_model=EsperaOut)
def retirar(espera_id: int, db: Session = Depends(get_db)):
    return svc.retirar(db, espera_id)


@router.post("/ofertas/{cita_id}/aceptar", response_model=CitaOut)
def aceptar(cita_id: int, db: Session = Depends(get_db)):
    return svc.aceptar_oferta(db, cita_id)


@router.post("/ofertas/{cita_id}/rechazar", status_code=204)
def rechazar(cita_id: int, db: Session = Depends(get_db)):
    svc.rechazar_oferta(db, cita_id)
