from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

EstadoCita = Literal["ofrecida", "programada", "confirmada", "cancelada", "atendida", "no_asistio"]


class Modelo(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Centros ----------
class CentroCrear(Modelo):
    nombre: str = Field(min_length=2)
    direccion: str
    ciudad: str
    telefono: str | None = None
    hora_apertura: time = time(7, 0)
    hora_cierre: time = time(18, 0)


class CentroActualizar(Modelo):
    nombre: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    telefono: str | None = None
    hora_apertura: time | None = None
    hora_cierre: time | None = None


class CentroOut(CentroCrear):
    id: int
    activo: bool


# ---------- Salas ----------
class SalaCrear(Modelo):
    centro_id: int
    nombre: str
    tipo: str = "consultorio"


class SalaActualizar(Modelo):
    nombre: str | None = None
    tipo: str | None = None


class SalaOut(SalaCrear):
    id: int
    activo: bool


# ---------- Médicos ----------
class MedicoCrear(Modelo):
    documento: str
    nombres: str
    apellidos: str
    especialidad: str
    email: EmailStr | None = None


class MedicoActualizar(Modelo):
    nombres: str | None = None
    apellidos: str | None = None
    especialidad: str | None = None
    email: EmailStr | None = None


class MedicoOut(MedicoCrear):
    id: int
    activo: bool


# ---------- Pacientes ----------
class PacienteCrear(Modelo):
    documento: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    email: EmailStr | None = None
    telefono: str | None = None
    canal_preferido: Literal["email", "whatsapp", "llamada"] = "email"
    atencion_asistida: bool = False

    @model_validator(mode="after")
    def validar(self):
        if not self.email and not self.telefono:
            raise ValueError("Se necesita al menos un correo o un teléfono")
        if self.fecha_nacimiento > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return self


class PacienteActualizar(Modelo):
    nombres: str | None = None
    apellidos: str | None = None
    email: EmailStr | None = None
    telefono: str | None = None
    canal_preferido: Literal["email", "whatsapp", "llamada"] | None = None
    atencion_asistida: bool | None = None


class PacienteOut(Modelo):
    id: int
    documento: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    email: str | None
    telefono: str | None
    canal_preferido: str
    atencion_asistida: bool
    activo: bool


# ---------- Citas ----------
class CitaCrear(Modelo):
    paciente_id: int
    medico_id: int
    centro_id: int
    sala_id: int | None = Field(None, description="Si se omite, se asigna una sala libre del centro")
    inicio: datetime
    duracion_min: int | None = Field(None, ge=10, le=240)
    motivo_consulta: str | None = None
    canal_origen: Literal["api", "web", "agente", "whatsapp", "call_center"] = "api"


class CitaReprogramar(Modelo):
    inicio: datetime


class CitaCancelar(Modelo):
    motivo: str = Field(min_length=3)


class CitaCambioEstado(Modelo):
    estado: Literal["confirmada", "atendida", "no_asistio"]


class CitaOut(Modelo):
    id: int
    paciente_id: int
    medico_id: int
    centro_id: int
    sala_id: int
    inicio: datetime
    fin: datetime
    duracion_min: int
    estado: str
    motivo_consulta: str | None
    motivo_cancelacion: str | None
    canal_origen: str
    oferta_expira_en: datetime | None


class Cupo(BaseModel):
    medico_id: int
    medico: str
    especialidad: str
    centro_id: int
    centro: str
    sala_id: int
    sala: str
    inicio: datetime
    fin: datetime


# ---------- Lista de espera ----------
class EsperaCrear(Modelo):
    paciente_id: int
    especialidad: str
    medico_id: int | None = None
    centro_id: int | None = None
    desde: date
    hasta: date

    @model_validator(mode="after")
    def validar(self):
        if self.hasta < self.desde:
            raise ValueError("'hasta' debe ser igual o posterior a 'desde'")
        return self


class EsperaOut(Modelo):
    id: int
    paciente_id: int
    especialidad: str
    medico_id: int | None
    centro_id: int | None
    desde: date
    hasta: date
    estado: str
    cita_ofrecida_id: int | None
