from sqlalchemy import select

from app import jobs
from app.config import settings
from app.models import Notificacion
from tests.conftest import cita


def test_recordatorio_se_envia_una_sola_vez(api, base, db, monkeypatch):
    monkeypatch.setattr(settings, "horas_recordatorio", 24 * 10)
    c = cita(api, base).json()
    assert jobs.enviar_recordatorios() == 1
    assert jobs.enviar_recordatorios() == 0   # idempotente: no repite
    tipos = [n.tipo for n in db.scalars(select(Notificacion).where(Notificacion.cita_id == c["id"]))]
    assert tipos.count("recordatorio") == 1


def test_canal_preferido_whatsapp_con_respaldo_por_correo(api, base, db):
    api.patch(f"/pacientes/{base['p'][0]['id']}", json={"canal_preferido": "whatsapp", "telefono": "300"})
    c = cita(api, base).json()
    canales = sorted(n.canal for n in db.scalars(select(Notificacion).where(Notificacion.cita_id == c["id"])))
    assert canales == ["email", "whatsapp"]


def test_redireccion_de_correos_en_modo_demo(monkeypatch, base, api):
    """En modo demostración todos los correos van a una sola dirección, avisando a quién iban."""
    enviados = []

    class SMTPFalso:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): enviados.append("tls")
        def login(self, u, c): enviados.append(("login", u))
        def send_message(self, msg): enviados.append((msg["To"], msg.get_body(("plain",)).get_content()))

    from app.services import notificaciones
    monkeypatch.setattr(notificaciones.smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(settings, "notificaciones_simuladas", False)
    monkeypatch.setattr(settings, "correo_redirigir_a", "demo@gmail.com")
    monkeypatch.setattr(settings, "smtp_tls", True)
    monkeypatch.setattr(settings, "smtp_usuario", "demo@gmail.com")
    monkeypatch.setattr(settings, "smtp_clave", "x")
    cita(api, base)
    assert enviados[0] == "tls" and enviados[1] == ("login", "demo@gmail.com")
    destino, cuerpo = enviados[2]
    assert destino == "demo@gmail.com" and "p1@correo.com.co" in cuerpo
