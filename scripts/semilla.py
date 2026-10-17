"""Datos de demostración: 2 centros, 5 salas, 5 médicos, 4 pacientes y algunas citas.
Uso:  python -m scripts.semilla"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.models import Centro, Medico, Paciente, Sala
from app.schemas import CitaCrear, EsperaCrear
from app.services import citas, lista_espera


def proximo_habil(dias: int) -> date:
    d = datetime.now(settings.tz).date() + timedelta(days=dias)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def main():
    with SessionLocal() as db:
        if db.execute(text("SELECT count(*) FROM centros")).scalar():
            print("La base ya tiene datos; no se siembra de nuevo.")
            return
        norte = Centro(nombre="Sede Norte", direccion="Calle 127 # 15-20", ciudad="Bogotá",
                       telefono="601 555 0101", hora_apertura=time(7), hora_cierre=time(17))
        chapinero = Centro(nombre="Sede Chapinero", direccion="Carrera 13 # 60-45", ciudad="Bogotá",
                           telefono="601 555 0202", hora_apertura=time(8), hora_cierre=time(18))
        db.add_all([norte, chapinero]); db.flush()
        db.add_all([Sala(centro_id=norte.id, nombre="Consultorio 101"),
                    Sala(centro_id=norte.id, nombre="Consultorio 102"),
                    Sala(centro_id=norte.id, nombre="Consultorio 103"),
                    Sala(centro_id=chapinero.id, nombre="Consultorio 201"),
                    Sala(centro_id=chapinero.id, nombre="Consultorio 202")])
        db.add_all([
            Medico(documento="80100100", nombres="Laura", apellidos="Gómez", especialidad="Medicina general", email="lgomez@centromedico.com.co"),
            Medico(documento="80100200", nombres="Andrés", apellidos="Rincón", especialidad="Medicina general", email="arincon@centromedico.com.co"),
            Medico(documento="80100300", nombres="Marta", apellidos="Salazar", especialidad="Cardiología", email="msalazar@centromedico.com.co"),
            Medico(documento="80100400", nombres="Jorge", apellidos="Pinzón", especialidad="Odontología", email="jpinzon@centromedico.com.co"),
            Medico(documento="80100500", nombres="Camila", apellidos="Herrera", especialidad="Pediatría", email="cherrera@centromedico.com.co"),
        ])
        db.add_all([
            Paciente(documento="41000111", nombres="Rosa", apellidos="Martínez", fecha_nacimiento=date(1948, 3, 12),
                     email="rosa.martinez@correo.com.co", telefono="3001112233", canal_preferido="email", atencion_asistida=True),
            Paciente(documento="1020304050", nombres="Daniel", apellidos="Ortiz", fecha_nacimiento=date(1992, 7, 2),
                     email="daniel.ortiz@correo.com.co", telefono="3104445566", canal_preferido="whatsapp"),
            Paciente(documento="52000222", nombres="Gloria", apellidos="Cárdenas", fecha_nacimiento=date(1955, 11, 20),
                     email="gloria.cardenas@correo.com.co", canal_preferido="email"),
            Paciente(documento="1030405060", nombres="Felipe", apellidos="Rojas", fecha_nacimiento=date(1988, 1, 15),
                     email="felipe.rojas@correo.com.co", telefono="3157778899", canal_preferido="email"),
        ])
        db.commit()

        manana = proximo_habil(1)
        def en(d, h, m=0):
            return datetime.combine(d, time(h, m), tzinfo=settings.tz)
        # Cardiología casi llena: crea la necesidad de lista de espera
        citas.crear_cita(db, CitaCrear(paciente_id=2, medico_id=3, centro_id=1, inicio=en(manana, 9), motivo_consulta="Control de presión"))
        citas.crear_cita(db, CitaCrear(paciente_id=4, medico_id=3, centro_id=1, inicio=en(manana, 10), motivo_consulta="Chequeo"))
        citas.crear_cita(db, CitaCrear(paciente_id=1, medico_id=1, centro_id=1, inicio=en(manana, 8), motivo_consulta="Control general"))
        lista_espera.unirse(db, EsperaCrear(paciente_id=3, especialidad="Cardiología",
                                            desde=datetime.now(settings.tz).date(), hasta=proximo_habil(10)))
        print("Datos de demostración cargados.")
        print("Pruebe el asistente con el documento 41000111 (Rosa, atención asistida) o 1020304050 (Daniel).")


if __name__ == "__main__":
    main()
