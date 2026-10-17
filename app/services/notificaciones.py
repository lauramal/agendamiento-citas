"""Notificaciones multicanal.

- Cada paciente elige su canal (email, WhatsApp, llamada): accesibilidad como dato.
- Los mensajes son cortos, en lenguaje simple, con UNA acción por botón.
- Pacientes con atención asistida reciben además un teléfono para ser atendidos
  por una persona: nadie queda obligado a usar una app.
- Todo lo enviado queda registrado (trazabilidad).

Canales: el correo se envía de verdad por SMTP (en local lo captura Mailpit).
WhatsApp y llamada quedan simulados detrás de la misma interfaz: integrarlos
es implementar un adaptador, no tocar la lógica de negocio.
"""
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Cita, Notificacion, Paciente
from app.services import tokens

log = logging.getLogger("notificaciones")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_humana(cita: Cita) -> str:
    f = cita.inicio.astimezone(settings.tz)
    hora = f.strftime("%I:%M %p").lstrip("0").replace("AM", "a. m.").replace("PM", "p. m.")
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month - 1]} a las {hora}"


# ---------- Canales ----------
class CanalEmail:
    nombre = "email"

    def enviar(self, paciente: Paciente, asunto: str, texto: str, html: str) -> tuple[str, str]:
        if not paciente.email:
            return "fallida", "El paciente no tiene correo"
        if settings.notificaciones_simuladas:
            return "simulada", "Envío simulado (modo pruebas)"
        destino = settings.correo_redirigir_a or paciente.email
        if settings.correo_redirigir_a:
            aviso = f"[Demostración] Este correo iba para {paciente.nombres} {paciente.apellidos} <{paciente.email}>."
            texto = f"{aviso}\n\n{texto}"
            html = f'<p style="font-family:Arial;font-size:13px;color:#666">{aviso}</p>{html}'
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = asunto, settings.smtp_remitente, destino
        msg.set_content(texto)
        msg.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
                if settings.smtp_tls:
                    s.starttls()
                if settings.smtp_usuario and settings.smtp_clave:
                    s.login(settings.smtp_usuario, settings.smtp_clave)
                s.send_message(msg)
            return "enviada", f"SMTP a {destino}"
        except (OSError, smtplib.SMTPException) as e:
            log.warning("No se pudo enviar correo: %s", e)
            return "fallida", str(e)


class CanalSimulado:
    """WhatsApp / llamada: misma interfaz, sin proveedor conectado en esta versión."""

    def __init__(self, nombre: str):
        self.nombre = nombre

    def enviar(self, paciente: Paciente, asunto: str, texto: str, html: str) -> tuple[str, str]:
        log.info("[%s simulado] a %s: %s", self.nombre, paciente.telefono, texto)
        return "simulada", f"Pendiente integrar proveedor de {self.nombre}"


CANALES = {"email": CanalEmail(), "whatsapp": CanalSimulado("whatsapp"),
           "llamada": CanalSimulado("llamada")}


def _plantilla_html(titulo: str, parrafos: list[str], botones: list[tuple[str, str, str]]) -> str:
    cuerpo = "".join(f'<p style="font-size:19px;line-height:1.5;margin:0 0 14px">{p}</p>' for p in parrafos)
    btns = "".join(
        f'<a href="{url}" style="display:block;text-align:center;font-size:20px;font-weight:700;'
        f'padding:16px;margin:10px 0;border-radius:10px;text-decoration:none;'
        f'background:{fondo};color:#fff">{texto}</a>' for texto, url, fondo in botones)
    return (f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#1d2a33">'
            f'<h1 style="font-size:24px">{titulo}</h1>{cuerpo}{btns}</div>')


def _enviar(db: Session, paciente: Paciente, cita: Cita | None, tipo: str,
            asunto: str, parrafos: list[str], botones: list[tuple[str, str, str]]) -> None:
    if paciente.atencion_asistida:
        parrafos = parrafos + ["Si prefiere, llámenos y una persona le ayuda con su cita."]
    texto = "\n\n".join(parrafos + [f"{t}: {u}" for t, u, _ in botones])
    html = _plantilla_html(asunto, parrafos, botones)

    canales = [CANALES[paciente.canal_preferido]]
    # Respaldo: si el canal preferido no es correo, también se envía por correo
    if paciente.canal_preferido != "email" and paciente.email:
        canales.append(CANALES["email"])

    for canal in canales:
        estado, detalle = canal.enviar(paciente, asunto, texto, html)
        db.add(Notificacion(paciente_id=paciente.id, cita_id=cita.id if cita else None,
                            canal=canal.nombre, tipo=tipo, estado=estado, detalle=detalle,
                            destino=paciente.email if canal.nombre == "email" else paciente.telefono))
    db.commit()


def _lugar(cita: Cita) -> str:
    return (f"Con {cita.medico.nombre_completo} ({cita.medico.especialidad}), "
            f"en {cita.centro.nombre}, {cita.sala.nombre}. Dirección: {cita.centro.direccion}.")


def confirmacion_agendamiento(db: Session, cita: Cita) -> None:
    p = cita.paciente
    _enviar(db, p, cita, "confirmacion", "Su cita quedó agendada", [
        f"Hola, {p.nombres}. Su cita quedó agendada para el {fecha_humana(cita)}.",
        _lugar(cita),
        "Un día antes le recordaremos la cita.",
    ], [("No puedo asistir: cancelar", tokens.url(cita.id, "cancelar"), "#9b3b2e")])


def recordatorio(db: Session, cita: Cita) -> None:
    p = cita.paciente
    _enviar(db, p, cita, "recordatorio", "Recordatorio de su cita", [
        f"Hola, {p.nombres}. Le recordamos su cita del {fecha_humana(cita)}.",
        _lugar(cita),
        "Por favor díganos si va a asistir. Si no puede, al cancelar le damos el turno a otra persona que lo necesita.",
    ], [("Sí, voy a asistir", tokens.url(cita.id, "confirmar"), "#1f6f54"),
        ("No puedo asistir", tokens.url(cita.id, "cancelar"), "#9b3b2e")])


def oferta_cupo(db: Session, cita: Cita) -> None:
    p = cita.paciente
    limite = cita.oferta_expira_en.astimezone(settings.tz).strftime("%I:%M %p").lstrip("0")
    _enviar(db, p, cita, "oferta_lista_espera", "Se liberó una cita para usted", [
        f"Hola, {p.nombres}. Se liberó un turno que estaba esperando: {fecha_humana(cita)}.",
        _lugar(cita),
        f"Se lo guardamos hasta las {limite}. Si no responde, pasa a la siguiente persona.",
    ], [("Tomar esta cita", tokens.url(cita.id, "aceptar_oferta"), "#1f6f54"),
        ("No me sirve este horario", tokens.url(cita.id, "rechazar_oferta"), "#5b6670")])
