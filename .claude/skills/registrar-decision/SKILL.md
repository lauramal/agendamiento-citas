---
name: registrar-decision
description: Documenta una decisión de diseño en docs/decisiones.md con el formato del proyecto (contexto, opciones, decisión, por qué e implicaciones) y la agrega a la tabla de decisiones del README. Úsalo siempre que se tome una decisión de arquitectura o se elija entre alternativas, o cuando el usuario pida explicar, justificar o documentar el porqué de algo, aunque no mencione decisiones.md.
---

# Registrar una decisión

Lo más valioso de este proyecto es el porqué de cada decisión y las alternativas que se descartaron. Una decisión sin su alternativa descartada no está documentada: solo está descrita.

## Pasos

1. Lee `docs/decisiones.md` y toma el siguiente número (si la última es D11, la nueva es D12). Si la decisión cambia una existente, edita esa en lugar de crear otra.
2. Agrega la decisión al final de `docs/decisiones.md`, después de un separador `---`, con esta estructura:

```markdown
## D12. Título corto, como tema o pregunta

**Contexto.** Qué problema hay y por qué importa. Una o dos frases con el riesgo real.

**Opciones.**
1. La más simple.
2. La intermedia.
3. La elegida.

**Decisión.** Cuál se eligió, en una frase.

**Por qué.** El problema concreto de cada opción descartada y la razón de la elegida. Si hay una prueba que lo demuestra, nómbrala.

**Implica.** Costos, requisitos o cambios futuros. Omite esta sección si no hay consecuencias.
```

3. Agrega una fila a la tabla de la sección "Decisiones de Diseño" del README, con las columnas `# | Decisión | Alternativa descartada | Por qué`. Cada celda debe caber en una línea corta.
4. Si la decisión cambia algo visible (una variable de entorno o un comportamiento), actualiza también la sección del README que lo explica.

## Criterios de calidad

- Cada opción descartada lleva su razón concreta. Evita "es más limpio" o "es mejor práctica": di qué falla, qué riesgo hay o qué cuesta.
- Mínimo dos opciones reales. Si solo hay una, no es una decisión, es un requisito.
- Escribe en español claro, en frases cortas y sin adjetivos de marketing.
- Una decisión por entrada, de unas 15 líneas como máximo.
- Si una prueba o un comando lo demuestra, cítalo por su nombre (por ejemplo `test_dos_reservas_simultaneas_solo_una_gana`).
