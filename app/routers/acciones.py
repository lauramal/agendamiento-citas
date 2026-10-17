"""Acciones desde el correo, pensadas para cualquier persona.

Decisión: el enlace del correo (GET) NO ejecuta la acción; muestra una página
con un solo botón grande, y el botón (POST) la ejecuta. Motivo: los filtros
antispam y antivirus de los correos abren los enlaces automáticamente para
revisarlos; si el GET cancelara, se cancelarían citas sin que el paciente
hiciera nada.
"""
from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.errores import ErrorNegocio
from app.services import citas as svc_citas
from app.services import lista_espera, tokens
from app.services.notificaciones import fecha_humana

router = APIRouter(prefix="/acciones", tags=["Acciones desde el correo"], include_in_schema=False)

TEXTOS = {
    "confirmar": ("¿Confirma que va a asistir?", "Sí, voy a asistir", "#1f6f54",
                  "Listo. Su cita quedó confirmada. Lo esperamos."),
    "cancelar": ("¿Quiere cancelar su cita?", "Sí, cancelar mi cita", "#9b3b2e",
                 "Su cita quedó cancelada. Gracias por avisar: el turno pasa a otra persona que lo necesita."),
    "aceptar_oferta": ("¿Quiere tomar esta cita?", "Sí, tomar la cita", "#1f6f54",
                       "Listo. La cita es suya y quedó confirmada."),
    "rechazar_oferta": ("¿Este horario no le sirve?", "No me sirve, sigo esperando", "#5b6670",
                        "Entendido. Sigue en la lista de espera y le avisaremos del próximo turno."),
}


def _pagina(titulo: str, cuerpo: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<style>
  body {{ font-family: Verdana, Arial, sans-serif; background:#f3f6f4; color:#17262e;
         margin:0; padding:24px; font-size:20px; line-height:1.55; }}
  main {{ max-width:560px; margin:6vh auto; background:#fff; border-radius:16px;
          padding:32px 28px; border:2px solid #d6e0dc; }}
  h1 {{ font-size:28px; line-height:1.25; margin:0 0 16px; }}
  button {{ width:100%; font-size:22px; font-weight:700; color:#fff; border:0;
            border-radius:12px; padding:20px; cursor:pointer; margin-top:12px; }}
  button:focus-visible {{ outline:4px solid #f2b705; outline-offset:3px; }}
  .detalle {{ background:#f3f6f4; border-radius:10px; padding:16px; margin:16px 0; }}
</style></head><body><main>{cuerpo}</main></body></html>""")


@router.get("/{token}", response_class=HTMLResponse)
def ver_accion(token: str, db: Session = Depends(get_db)):
    try:
        cita_id, accion = tokens.leer(token)
        cita = svc_citas.obtener_cita(db, cita_id)
    except ErrorNegocio as e:
        return _pagina("Enlace no válido", f"<h1>{escape(e.mensaje)}</h1>")
    pregunta, boton, color, _ = TEXTOS[accion]
    detalle = (f"<div class='detalle'><strong>{escape(fecha_humana(cita))}</strong><br>"
               f"{escape(cita.medico.nombre_completo)} · {escape(cita.medico.especialidad)}<br>"
               f"{escape(cita.centro.nombre)} · {escape(cita.sala.nombre)}</div>")
    return _pagina(pregunta, f"""<h1>{escape(pregunta)}</h1>{detalle}
<form method="post"><button style="background:{color}">{escape(boton)}</button></form>""")


@router.post("/{token}", response_class=HTMLResponse)
def ejecutar_accion(token: str, db: Session = Depends(get_db)):
    try:
        cita_id, accion = tokens.leer(token)
        if accion == "confirmar":
            svc_citas.cambiar_estado(db, cita_id, "confirmada", "email", "Confirmada desde el recordatorio")
        elif accion == "cancelar":
            svc_citas.cancelar(db, cita_id, "Cancelada por el paciente desde el correo", "email")
        elif accion == "aceptar_oferta":
            lista_espera.aceptar_oferta(db, cita_id, "email")
        elif accion == "rechazar_oferta":
            lista_espera.rechazar_oferta(db, cita_id, "email")
    except ErrorNegocio as e:
        return _pagina("No fue posible", f"<h1>No fue posible</h1><p>{escape(e.mensaje)}</p>")
    return _pagina("Listo", f"<h1>Listo</h1><p>{escape(TEXTOS[accion][3])}</p>")
