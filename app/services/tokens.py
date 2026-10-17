"""Enlaces firmados para actuar desde un correo sin iniciar sesión.

El token lleva la cita y la acción, firmado con un secreto del servidor:
nadie puede fabricar uno para otra cita. Caduca solo.
"""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.errores import ErrorNegocio

ACCIONES = {"confirmar", "cancelar", "aceptar_oferta", "rechazar_oferta"}
_firmador = URLSafeTimedSerializer(settings.secreto_enlaces, salt="acciones-cita")


def generar(cita_id: int, accion: str) -> str:
    assert accion in ACCIONES
    return _firmador.dumps({"c": cita_id, "a": accion})


def leer(token: str, max_dias: int = 15) -> tuple[int, str]:
    try:
        datos = _firmador.loads(token, max_age=max_dias * 86400)
    except SignatureExpired as e:
        raise ErrorNegocio("Este enlace ya venció.", 410) from e
    except BadSignature as e:
        raise ErrorNegocio("El enlace no es válido.", 400) from e
    return int(datos["c"]), str(datos["a"])


def url(cita_id: int, accion: str) -> str:
    return f"{settings.url_publica}/acciones/{generar(cita_id, accion)}"
