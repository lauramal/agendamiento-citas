"""Mapeo ORM del esquema. El esquema real (con sus restricciones) vive en
sql/001_esquema.sql: la base de datos es la fuente de verdad de las reglas."""
from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, DateTime, FetchedValue, ForeignKey, Integer, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Centro(Base):
    __tablename__ = "centros"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    direccion: Mapped[str] = mapped_column(Text)
    ciudad: Mapped[str] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    hora_apertura: Mapped[time] = mapped_column(Time, server_default=FetchedValue())
    hora_cierre: Mapped[time] = mapped_column(Time, server_default=FetchedValue())
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    salas: Mapped[list["Sala"]] = relationship(back_populates="centro")


class Sala(Base):
    __tablename__ = "salas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros.id"))
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text, default="consultorio")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    centro: Mapped[Centro] = relationship(back_populates="salas")


class Medico(Base):
    __tablename__ = "medicos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento: Mapped[str] = mapped_column(Text)
    nombres: Mapped[str] = mapped_column(Text)
    apellidos: Mapped[str] = mapped_column(Text)
    especialidad: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}"


class Paciente(Base):
    __tablename__ = "pacientes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento: Mapped[str] = mapped_column(Text)
    nombres: Mapped[str] = mapped_column(Text)
    apellidos: Mapped[str] = mapped_column(Text)
    fecha_nacimiento: Mapped[date] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    canal_preferido: Mapped[str] = mapped_column(Text, default="email")
    atencion_asistida: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Cita(Base):
    __tablename__ = "citas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    medico_id: Mapped[int] = mapped_column(ForeignKey("medicos.id"))
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros.id"))
    sala_id: Mapped[int] = mapped_column(ForeignKey("salas.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duracion_min: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(Text, default="programada")
    motivo_consulta: Mapped[str | None] = mapped_column(Text)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text)
    canal_origen: Mapped[str] = mapped_column(Text, default="api")
    oferta_expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recordatorio_enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())

    paciente: Mapped[Paciente] = relationship()
    medico: Mapped[Medico] = relationship()
    centro: Mapped[Centro] = relationship()
    sala: Mapped[Sala] = relationship()


class CitaHistorial(Base):
    __tablename__ = "citas_historial"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cita_id: Mapped[int] = mapped_column(ForeignKey("citas.id"))
    estado_anterior: Mapped[str | None] = mapped_column(Text)
    estado_nuevo: Mapped[str] = mapped_column(Text)
    detalle: Mapped[str | None] = mapped_column(Text)
    canal: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class ListaEspera(Base):
    __tablename__ = "lista_espera"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    especialidad: Mapped[str] = mapped_column(Text)
    medico_id: Mapped[int | None] = mapped_column(ForeignKey("medicos.id"))
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id"))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Text, default="esperando")
    cita_ofrecida_id: Mapped[int | None] = mapped_column(ForeignKey("citas.id"))
    creado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    paciente: Mapped[Paciente] = relationship()


class Notificacion(Base):
    __tablename__ = "notificaciones"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    cita_id: Mapped[int | None] = mapped_column(ForeignKey("citas.id"))
    canal: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    destino: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text)
    detalle: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
