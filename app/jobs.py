"""Tareas automáticas. Corren dentro del mismo proceso (APScheduler) por
simplicidad; en producción irían en un worker aparte o en Cloud Scheduler."""
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Cita
from app.services import lista_espera, notificaciones
from app.services.citas import ahora

log = logging.getLogger("jobs")


def enviar_recordatorios() -> int:
    with SessionLocal() as db:
        limite = ahora() + timedelta(hours=settings.horas_recordatorio)
        pendientes = db.scalars(select(Cita).where(
            Cita.estado == "programada", Cita.recordatorio_enviado_en.is_(None),
            Cita.inicio > ahora(), Cita.inicio <= limite)).all()
        for cita in pendientes:
            notificaciones.recordatorio(db, cita)
            cita.recordatorio_enviado_en = ahora()
            db.commit()
        return len(pendientes)


def vencer_ofertas() -> int:
    with SessionLocal() as db:
        return lista_espera.expirar_ofertas(db)


def iniciar() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=settings.zona_horaria)
    sched.add_job(enviar_recordatorios, "interval", minutes=5, id="recordatorios")
    sched.add_job(vencer_ofertas, "interval", minutes=1, id="ofertas")
    sched.start()
    log.info("Tareas automáticas iniciadas")
    return sched
