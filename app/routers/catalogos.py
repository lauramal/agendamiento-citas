"""CRUD de pacientes, médicos, centros y salas.

Eliminar = desactivar (borrado lógico): en salud el historial no se borra.
Un registro desactivado no aparece en disponibilidad ni recibe citas nuevas,
pero sus citas pasadas siguen consultables.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.errores import ErrorNegocio, NoEncontrado, traducir_integridad
from app.models import Centro, Cita, Medico, Paciente, Sala
from app.schemas import (CentroActualizar, CentroCrear, CentroOut, MedicoActualizar, MedicoCrear,
                         MedicoOut, PacienteActualizar, PacienteCrear, PacienteOut, SalaActualizar,
                         SalaCrear, SalaOut)
from app.services.citas import ESTADOS_ACTIVOS, ahora


def _guardar(db: Session, obj):
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise traducir_integridad(e) from e
    db.refresh(obj)
    return obj


def _obtener(db: Session, modelo, id_: int, nombre: str):
    obj = db.get(modelo, id_)
    if not obj:
        raise NoEncontrado(nombre)
    return obj


def _actualizar(db: Session, obj, datos):
    for k, v in datos.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    return _guardar(db, obj)


def _tiene_citas_futuras(db: Session, columna, id_: int) -> bool:
    return db.scalar(select(Cita.id).where(columna == id_, Cita.estado.in_(ESTADOS_ACTIVOS),
                                           Cita.inicio > ahora()).limit(1)) is not None


# ---------- Pacientes ----------
pacientes = APIRouter(prefix="/pacientes", tags=["Pacientes"])


@pacientes.post("", response_model=PacienteOut, status_code=201)
def crear_paciente(datos: PacienteCrear, db: Session = Depends(get_db)):
    return _guardar(db, Paciente(**datos.model_dump()))


@pacientes.get("", response_model=list[PacienteOut])
def listar_pacientes(documento: str | None = None, incluir_inactivos: bool = False,
                     db: Session = Depends(get_db)):
    q = select(Paciente)
    if documento:
        q = q.where(Paciente.documento == documento)
    if not incluir_inactivos:
        q = q.where(Paciente.activo.is_(True))
    return db.scalars(q.order_by(Paciente.id)).all()


@pacientes.get("/{id_}", response_model=PacienteOut)
def ver_paciente(id_: int, db: Session = Depends(get_db)):
    return _obtener(db, Paciente, id_, "El paciente")


@pacientes.patch("/{id_}", response_model=PacienteOut)
def actualizar_paciente(id_: int, datos: PacienteActualizar, db: Session = Depends(get_db)):
    return _actualizar(db, _obtener(db, Paciente, id_, "El paciente"), datos)


@pacientes.delete("/{id_}", response_model=PacienteOut)
def eliminar_paciente(id_: int, db: Session = Depends(get_db)):
    p = _obtener(db, Paciente, id_, "El paciente")
    if _tiene_citas_futuras(db, Cita.paciente_id, id_):
        raise ErrorNegocio("El paciente tiene citas próximas. Cancélelas antes de desactivarlo.", 409)
    p.activo = False
    return _guardar(db, p)


# ---------- Médicos ----------
medicos = APIRouter(prefix="/medicos", tags=["Médicos"])


@medicos.post("", response_model=MedicoOut, status_code=201)
def crear_medico(datos: MedicoCrear, db: Session = Depends(get_db)):
    return _guardar(db, Medico(**datos.model_dump()))


@medicos.get("", response_model=list[MedicoOut])
def listar_medicos(especialidad: str | None = Query(None), db: Session = Depends(get_db)):
    q = select(Medico).where(Medico.activo.is_(True))
    if especialidad:
        q = q.where(Medico.especialidad.ilike(especialidad))
    return db.scalars(q.order_by(Medico.id)).all()


@medicos.get("/{id_}", response_model=MedicoOut)
def ver_medico(id_: int, db: Session = Depends(get_db)):
    return _obtener(db, Medico, id_, "El médico")


@medicos.patch("/{id_}", response_model=MedicoOut)
def actualizar_medico(id_: int, datos: MedicoActualizar, db: Session = Depends(get_db)):
    return _actualizar(db, _obtener(db, Medico, id_, "El médico"), datos)


@medicos.delete("/{id_}", response_model=MedicoOut)
def eliminar_medico(id_: int, db: Session = Depends(get_db)):
    m = _obtener(db, Medico, id_, "El médico")
    if _tiene_citas_futuras(db, Cita.medico_id, id_):
        raise ErrorNegocio("El médico tiene citas próximas. Reasígnelas antes de desactivarlo.", 409)
    m.activo = False
    return _guardar(db, m)


# ---------- Centros ----------
centros = APIRouter(prefix="/centros", tags=["Centros de atención"])


@centros.post("", response_model=CentroOut, status_code=201)
def crear_centro(datos: CentroCrear, db: Session = Depends(get_db)):
    return _guardar(db, Centro(**datos.model_dump()))


@centros.get("", response_model=list[CentroOut])
def listar_centros(db: Session = Depends(get_db)):
    return db.scalars(select(Centro).where(Centro.activo.is_(True)).order_by(Centro.id)).all()


@centros.get("/{id_}", response_model=CentroOut)
def ver_centro(id_: int, db: Session = Depends(get_db)):
    return _obtener(db, Centro, id_, "El centro de atención")


@centros.patch("/{id_}", response_model=CentroOut)
def actualizar_centro(id_: int, datos: CentroActualizar, db: Session = Depends(get_db)):
    return _actualizar(db, _obtener(db, Centro, id_, "El centro de atención"), datos)


@centros.delete("/{id_}", response_model=CentroOut)
def eliminar_centro(id_: int, db: Session = Depends(get_db)):
    c = _obtener(db, Centro, id_, "El centro de atención")
    if _tiene_citas_futuras(db, Cita.centro_id, id_):
        raise ErrorNegocio("El centro tiene citas próximas. Reubíquelas antes de desactivarlo.", 409)
    c.activo = False
    return _guardar(db, c)


# ---------- Salas ----------
salas = APIRouter(prefix="/salas", tags=["Salas"])


@salas.post("", response_model=SalaOut, status_code=201)
def crear_sala(datos: SalaCrear, db: Session = Depends(get_db)):
    _obtener(db, Centro, datos.centro_id, "El centro de atención")
    return _guardar(db, Sala(**datos.model_dump()))


@salas.get("", response_model=list[SalaOut])
def listar_salas(centro_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Sala).where(Sala.activo.is_(True))
    if centro_id:
        q = q.where(Sala.centro_id == centro_id)
    return db.scalars(q.order_by(Sala.id)).all()


@salas.get("/{id_}", response_model=SalaOut)
def ver_sala(id_: int, db: Session = Depends(get_db)):
    return _obtener(db, Sala, id_, "La sala")


@salas.patch("/{id_}", response_model=SalaOut)
def actualizar_sala(id_: int, datos: SalaActualizar, db: Session = Depends(get_db)):
    return _actualizar(db, _obtener(db, Sala, id_, "La sala"), datos)


@salas.delete("/{id_}", response_model=SalaOut)
def eliminar_sala(id_: int, db: Session = Depends(get_db)):
    s = _obtener(db, Sala, id_, "La sala")
    if _tiene_citas_futuras(db, Cita.sala_id, id_):
        raise ErrorNegocio("La sala tiene citas próximas. Reubíquelas antes de desactivarla.", 409)
    s.activo = False
    return _guardar(db, s)
