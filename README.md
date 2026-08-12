# Radar CGR

Módulo OSINT para transformar información pública de la **Contraloría General de la República de Chile (CGR)** en datos estructurados, trazables y reutilizables para inteligencia de riesgo con enfoque AML/LA-FT.

> **Regla de interpretación:** una observación CGR, la aparición de un proveedor o una hipótesis de relevancia penal **no acredita por sí sola lavado de activos, delito ni responsabilidad individual**. El sistema prioriza revisión y conserva siempre la evidencia oficial.

## v0.2 — Entity & Irregularity Intelligence

La v0.2 cambia la unidad de análisis desde el documento hacia las entidades y hechos relacionados. El Radar busca responder preguntas como:

- ¿Qué organismo público aparece involucrado en irregularidades?
- ¿En qué región se ubica?
- ¿El hallazgo involucra proveedores o entidades privadas?
- ¿Qué proveedores aparecen en más de un organismo o documento?
- ¿Qué tipologías de irregularidad se repiten?
- ¿Qué casos tienen reparo, procedimiento disciplinario o remisión al Ministerio Público/CDE?
- ¿Qué hallazgos presentan indicadores compatibles con una posible hipótesis de relevancia penal funcionaria?

## Arquitectura sin servidor

```text
CGR publica
   |
   v
collectors Python / GitHub Actions
   |
   +--> data/bronze/ snapshots de fuente
   +--> data/silver/ evidencia y tablas maestras JSONL
   +--> data/gold/ Parquet analítico
   +--> docs/data/dashboard.json
   |
   v
GitHub Pages
```

No requiere PostgreSQL, VM ni backend adicional. La estructura queda preparada para migrar a SQL/PostgreSQL en una evolución futura.

## Modelo de datos

### Evidencia primaria

```text
documents -> events -> findings -> evidence
```

### Inteligencia derivada v0.2

```text
organizations
providers
persons
relationships
irregularities
penal_hypotheses
finding_enrichment
```

Las tablas derivadas se **reconstruyen de manera determinista** desde la evidencia primaria. Esto permite mejorar las reglas sin alterar el documento fuente ni acumular clasificaciones obsoletas.

## Tres dimensiones separadas

- **CGR Risk:** gravedad administrativa/fiscal del hallazgo según tipología, monto y acciones posteriores.
- **Penal Relevance:** intensidad de indicadores compatibles con una eventual relevancia penal. Distingue inferencia analítica de remisiones explícitas efectuadas por CGR.
- **AML Relevance:** interés del hallazgo para priorización desde perspectiva AML/LA-FT.

Los proveedores poseen adicionalmente un **Exposure Recurrence Score**. Este indicador mide recurrencia documental y diversidad de organismos; **no representa culpabilidad ni riesgo penal del proveedor**.

## Tipologías iniciales

Incluye, entre otras: pagos improcedentes; pagos/gastos sin respaldo; prestaciones no acreditadas; contratación irregular; trato directo; conflicto de interés/inhabilidad; partes relacionadas; sobrepagos; fondos sin rendición; uso de fondos para fines distintos; anomalías contables; inconsistencias documentales; beneficiarios con requisitos observados; fallas de control; irregularidades de personal; control de activos.

## Hipótesis de relevancia penal

La versión inicial identifica, siempre como **hipótesis para revisión**, patrones compatibles con posible fraude al Fisco, malversación de caudales públicos, negociación incompatible, cohecho solo ante referencias explícitas, relevancia penal documental y otras materias cuando CGR remite expresamente antecedentes al Ministerio Público.

Cada hipótesis incluye `score`, `evidence_level`, fundamentos, limitaciones y vínculo a la evidencia CGR.

## Actualización

`.github/workflows/radar.yml` ejecuta pruebas y el pipeline dos veces al día. En cada corrida consulta fuentes CGR, actualiza documentos/hallazgos/evidencia, reconstruye la inteligencia de entidades, recalcula perfiles, exporta JSONL/Parquet, genera `docs/data/dashboard.json` y persiste únicamente cambios reales.

También puede reconstruirse todo sin red:

```bash
python run.py --skip-network
```

## Dashboard v0.2

La interfaz incorpora Resumen ejecutivo, Organismos, Proveedores, Territorio, Posible relevancia penal, Hallazgos, Salud de fuentes y fichas emergentes con trazabilidad a CGR.

## Próximas líneas

- ampliar resolución de organismos y alias institucionales;
- extracción de RUT cuando la evidencia oficial lo exponga;
- mayor cobertura de personas/cargos sin fabricar identidades ausentes;
- especialización de Fiscalizaciones en Curso (`WATCH -> FINDING`);
- taxonomía FAU computable;
- Tribunal de Cuentas como capa de enforcement;
- CIC como señales de cruces masivos;
- lectura PDF cuando HTML no sea suficiente;
- Entity Hub común con otros módulos AML.
