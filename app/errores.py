"""Errores de negocio y traducción de las restricciones de la base de datos
a mensajes que entiende una persona (y el agente)."""
from sqlalchemy.exc import IntegrityError


class ErrorNegocio(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        self.mensaje = mensaje
        self.codigo = codigo
        super().__init__(mensaje)


class NoEncontrado(ErrorNegocio):
    def __init__(self, recurso: str):
        super().__init__(f"{recurso} no existe", 404)


MENSAJES_RESTRICCION = {
    "medico_sin_traslape": "El médico ya tiene una cita en ese horario.",
    "sala_sin_traslape": "La sala ya está ocupada en ese horario.",
    "paciente_sin_traslape": "El paciente ya tiene otra cita en ese horario.",
    "sala_del_centro": "La sala no pertenece a ese centro de atención.",
    "cancelar_con_motivo": "Para cancelar una cita hay que indicar el motivo.",
    "contacto_minimo": "El paciente necesita al menos un correo o un teléfono.",
    "pacientes_documento_key": "Ya existe un paciente con ese documento.",
    "medicos_documento_key": "Ya existe un médico con ese documento.",
    "centros_nombre_key": "Ya existe un centro con ese nombre.",
    "sala_unica_por_centro": "Ya existe una sala con ese nombre en el centro.",
    "horario_valido": "La hora de cierre debe ser posterior a la de apertura.",
}


def traducir_integridad(error: IntegrityError) -> ErrorNegocio:
    texto = str(error.orig)
    for restriccion, mensaje in MENSAJES_RESTRICCION.items():
        if restriccion in texto:
            return ErrorNegocio(mensaje, 409)
    return ErrorNegocio("La operación viola una regla de integridad de los datos.", 409)
