---
name: nueva-regla-de-negocio
description: Agrega una regla de negocio o validación al sistema de citas médicas dejándola en la base de datos y no solo en el código. Úsalo siempre que se pida una nueva validación, restricción, límite o regla (por ejemplo "no permitir X", "limitar Y", "exigir Z al cancelar", "que la duración sea múltiplo de 5"), aunque el usuario no mencione la base de datos, el esquema ni las pruebas.
---

# Nueva regla de negocio

Una regla en este proyecto toca cuatro lugares: el esquema, el mensaje de error, el servicio y las pruebas. Olvidar uno deja la regla a medias. Por eso está escrita como procedimiento.

## Principio

Si la regla se puede expresar como restricción de PostgreSQL (CHECK, UNIQUE, EXCLUDE o clave foránea), va en la base de datos. Validar solo en el código tiene condición de carrera: dos peticiones simultáneas pasan la verificación y las dos guardan (decisión D1 en `docs/decisiones.md`). La validación en el código se agrega únicamente para dar un mensaje claro antes de llegar a la base, nunca en su lugar.

Si la regla depende del reloj o del contexto de la petición y SQL no la puede garantizar (por ejemplo, la anticipación mínima para cancelar), va en el servicio, y se deja anotado el porqué.

## Pasos

1. Escribe la restricción en `sql/001_esquema.sql`, dentro de la tabla que corresponda. Ese archivo es la única fuente de verdad: Docker lo carga al crear la base y las pruebas lo cargan en cada sesión. Nombra la restricción en snake_case describiendo la regla (`duracion_multiplo_de_5`).
2. Agrega el mensaje en `MENSAJES_RESTRICCION` de `app/errores.py`. La clave es el nombre exacto de la restricción y el texto lo debe entender una persona, sin términos técnicos. `traducir_integridad` busca cada clave dentro del texto del error de PostgreSQL y devuelve el primer mensaje que coincida, así que ningún nombre de restricción debe contener a otro.
3. Si la regla también describe la forma de un dato de entrada (un rango o un formato), refléjala en `app/schemas.py` para que el rechazo sea inmediato. La base de datos sigue siendo la que garantiza.
4. Si la persona necesita saber algo antes de intentar guardar, agrega la comprobación en `app/services/citas.py` antes de `db.flush()`. Solo para el mensaje: la base queda como guardián.
5. Escribe la prueba en `tests/`, con las fixtures `api` y `base` y el helper `cita` de `tests/conftest.py`:
   - un caso que viola la regla: espera el código 409 y el mensaje exacto de `MENSAJES_RESTRICCION`;
   - el caso límite que debe seguir pasando: espera 201.

   Si la regla es sensible a la concurrencia, copia el patrón de `test_dos_reservas_simultaneas_solo_una_gana` (varios hilos y un solo ganador).
6. Corre `pytest`. Necesita PostgreSQL: `docker compose up -d db` y crear la base `citas_test` (ver el README).
7. Si la regla es una decisión de diseño con alternativas reales, regístrala con el skill `registrar-decision`.

## Trampas conocidas

- No uses el operador `%` en `sql/001_esquema.sql`. Las pruebas cargan el esquema con psycopg, que lo toma como un parámetro y falla con `incomplete placeholder`. Usa `mod(a, b)` en lugar de `a % b`.
- El esquema solo se ejecuta cuando la base está vacía. En una base ya creada, aplica el `ALTER TABLE ... ADD CONSTRAINT` a mano, o recrea todo con `docker compose down -v` (borra los datos de demostración). El proyecto todavía no usa migraciones versionadas.
- Un CHECK nuevo falla si ya hay filas que lo violan. Revisa los datos antes de aplicarlo.
- Un CHECK no puede consultar otras tablas. Para eso usa una clave foránea o la validación en el servicio.

## Ejemplo completo

Regla: la duración de una cita debe ser múltiplo de 5 minutos.

Esquema, dentro de `CREATE TABLE citas`:

```sql
CONSTRAINT duracion_multiplo_de_5 CHECK (mod(duracion_min, 5) = 0),
```

`app/errores.py`, dentro de `MENSAJES_RESTRICCION`:

```python
"duracion_multiplo_de_5": "La duración de la cita debe ser múltiplo de 5 minutos.",
```

`tests/test_citas.py`:

```python
def test_duracion_multiplo_de_5(api, base):
    r = cita(api, base, duracion_min=33)
    assert r.status_code == 409
    assert r.json()["detalle"] == "La duración de la cita debe ser múltiplo de 5 minutos."
    assert cita(api, base, duracion_min=35).status_code == 201   # el límite válido sigue pasando
```
