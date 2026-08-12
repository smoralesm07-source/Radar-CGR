# Radar CGR

Radar OSINT para transformar información pública de la **Contraloría General de la República de Chile (CGR)** en datos estructurados, trazables y reutilizables para inteligencia de riesgo con enfoque AML/LA-FT.

> Una observación CGR, una coincidencia FAU o una hipótesis de relevancia penal no acredita por sí sola lavado de activos, delito, dolo ni responsabilidad individual. El sistema prioriza revisión y conserva la evidencia oficial.

## v0.3 — Enforcement & Temporal Intelligence

La v0.3 incorpora cuatro capacidades principales:

1. **Temporalidad del hallazgo:** separa la fecha/período de ocurrencia de la fecha de publicación del informe.
2. **Early Warning:** mantiene señales `WATCH` provenientes de Fiscalizaciones en Curso y de la capa de Tribunal de Cuentas, con matching posterior contra informes publicados.
3. **Enforcement:** modela procedimientos disciplinarios, reparos, remisiones al Ministerio Público y remisiones al CDE como eventos independientes.
4. **FAU computable:** clasifica hallazgos contra temas públicos de las Fichas de Alerta de Posibles Fraudes mediante reglas determinísticas y auditables.

## Temporalidad

Cada hallazgo incorpora:

```text
occurrence_date_from
occurrence_date_to
occurrence_date_anchor
occurrence_date_precision
occurrence_date_basis
occurrence_date_confidence
```

`occurrence_date_precision` distingue `EXACT`, `AS_OF_DATE`, `MONTH`, `YEAR`, `YEAR_RANGE`, `RANGE`, sus variantes `AUDIT_*` cuando el dato se hereda del período auditado y `UNKNOWN` cuando no existe evidencia temporal suficiente.

**Regla crítica:** la fecha del informe CGR nunca se usa automáticamente como fecha de ocurrencia. Cuando el hallazgo no entrega fecha propia, el sistema puede heredar el período declarado en el objetivo de la auditoría, con menor nivel de confianza.

Esto permite diferenciar, por ejemplo:

```text
Ocurrencia: 2024-01-01 → 2024-12-31
Publicación CGR: 2026-06-06
Enforcement: 2026-06-06 · REPARO / MP / CDE
```

## Modelo v0.3

```text
SOURCE
  |
  +--> WATCH_ITEM ---------> REPORT_PUBLISHED
  |                              |
  |                         DOCUMENT
  |                              |
  |                           FINDING
  |                    _________|_________
  |                   |         |         |
  |              TEMPORALITY  ENTITY   IRREGULARITY
  |                   |                   |
  |                   |                 FAU MATCH
  |                   |
  |              ENFORCEMENT EVENT
  |             /       |       |       \
  |      DISCIPLINE   REPARO    MP       CDE
  |                     |
  +----------------> TRIBUNAL WATCH
```

### Tablas primarias y derivadas

- `documents`
- `events`
- `findings`
- `evidence`
- `organizations`
- `providers`
- `persons`
- `relationships`
- `irregularities`
- `penal_hypotheses`
- `finding_enrichment`
- `watch_items`
- `enforcement_events`
- `fau_catalog`
- `fau_matches`
- `source_runs`

Las tablas derivadas se regeneran desde evidencia primaria para evitar clasificaciones históricas obsoletas.

## Early Warning

La capa `watch_items` procesa señales de:

- Fiscalizaciones en Curso.
- Tribunal de Cuentas / estado diario y juicios.

Una señal permanece como `WATCH` mientras no exista un informe compatible. Cuando el motor encuentra suficiente solapamiento documental, pasa a `REPORT_PUBLISHED` y conserva `matched_document_id` y `match_confidence`.

El matching es analítico, no una identidad jurídica garantizada; por ello mantiene score y evidencia de origen.

## Enforcement

`enforcement_events` separa la acción posterior del hallazgo:

- `DISCIPLINARY`
- `REPARO`
- `CRIMINAL_REFERRAL`
- `CDE_REFERRAL`

Para reparos se crea además `tribunal_link_status=PENDING_TRIBUNAL_LINK`, preparando la vinculación posterior con causas del Tribunal de Cuentas.

## FAU computable

La primera taxonomía computable considera temas públicos asociados a:

- remuneraciones y pagos a personal;
- adquisiciones y contratación pública;
- administración de cuentas corrientes y fondos;
- horas extraordinarias y control de jornada;
- pagos a proveedores y acreditación de prestaciones.

Cada match mantiene `pattern_code`, score, evidencia textual, origen y URL oficial del hallazgo. La coincidencia no equivale a una calificación de fraude efectuada por CGR.

## Dashboard

La interfaz v0.3 agrega:

- Cronología con filtro `desde/hasta` por solapamiento del intervalo de ocurrencia.
- Cobertura y precisión temporal.
- Alertas tempranas `WATCH → INFORME`.
- Vista de Enforcement con fecha de acción separada de la fecha del hallazgo.
- Catálogo y coincidencias FAU.
- Período observado en fichas de organismos y proveedores.

## Ejecución

El pipeline continúa funcionando sin servidor mediante GitHub Actions y GitHub Pages.

```bash
python run.py --skip-network
```

El modo sin red permite recalcular temporalidad, Entity Resolution, enforcement, FAU y dashboard usando el histórico ya persistido.

## Próximas extensiones

- identificación granular de causas del Tribunal de Cuentas y sentencia/estado;
- extracción de personas y RUT desde PDF/anexos cuando la fuente los publique;
- PDF Agent para casos donde el HTML no entregue suficiente granularidad;
- vinculación con un Entity Hub común a otros radares AML/LA-FT;
- scoring longitudinal por recurrencia real en ventanas temporales configurables.
