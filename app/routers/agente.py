import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errores import ErrorNegocio
from app.models import Paciente

router = APIRouter(prefix="/agente", tags=["Asistente conversacional"])


class Mensaje(BaseModel):
    documento: str = Field(description="Documento del paciente. En producción: sesión autenticada u OTP.")
    mensaje: str = Field(min_length=1, max_length=1000)
    conversacion_id: str | None = None


class Respuesta(BaseModel):
    respuesta: str
    conversacion_id: str


@router.post("/chat", response_model=Respuesta)
def chat(datos: Mensaje, db: Session = Depends(get_db)):
    if not settings.anthropic_api_key:
        raise ErrorNegocio("El asistente está desactivado: configure ANTHROPIC_API_KEY en el archivo .env. "
                           "El resto del sistema funciona sin él.", 503)
    paciente = db.scalar(select(Paciente).where(Paciente.documento == datos.documento,
                                                Paciente.activo.is_(True)))
    if not paciente:
        raise ErrorNegocio("No encontramos un paciente con ese documento.", 404)
    from app.agente.sofia import conversar   # import diferido: la API no depende del LLM para arrancar
    conv = datos.conversacion_id or uuid.uuid4().hex[:12]
    return Respuesta(respuesta=conversar(paciente.id, datos.mensaje, conv), conversacion_id=conv)
