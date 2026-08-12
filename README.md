# Radar CGR

Módulo OSINT para convertir información pública de la **Contraloría General de la República de Chile (CGR)** en datos estructurados, trazables y reutilizables para análisis de riesgo con enfoque AML/LA-FT.

> **Criterio de uso:** una observación de Contraloría, una fiscalización o una señal derivada por el sistema **no constituye por sí sola evidencia de lavado de activos, financiamiento del terrorismo ni responsabilidad penal**. El scoring se utiliza para priorización analítica y siempre debe conservarse la evidencia de origen.

## v0.1

Implementa Python + GitHub Actions + GitHub Pages, JSONL como capa maestra versionable, Parquet analítico, identificadores estables para documentos/eventos/hallazgos/entidades/evidencia, parser dedicado de fichas HTML de auditoría CGR, extracción de montos CLP, medidas posteriores y familias de riesgo AML explicables, descubrimiento de informes desde páginas oficiales y control de salud de fuentes.

## Arquitectura

```text
CGR publica
   |
   v
collectors Python
   |
   +--> data/bronze/  snapshots + hashes
   +--> data/silver/  JSONL: documents/events/findings/evidence/entities/relationships/source_runs
   +--> data/gold/    Parquet
   +--> docs/data/dashboard.json -> GitHub Pages
```

## Fuentes configuradas

`config/sources.json` contempla Noticias CGR, Informes de Auditoría, Fiscalizaciones en curso, FAU, Tribunal de Cuentas, auditorías de transferencias relacionadas con fundaciones, Semáforo Municipal, bases municipales y reportes financieros/presupuestarios.

La v0.1 prioriza extracción detallada de auditorías y descubrimiento desde fuentes oficiales. Los demás conectores ya generan control de salud y snapshots y se especializarán sin cambiar el modelo de datos.

## Trazabilidad

```text
document_id -> event_id -> finding_id -> evidence_id -> source_url / source_text / hash
```

## Ejecución

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
python run.py
```

`python run.py --skip-network` reconstruye salidas sin consultar Internet. `python run.py --source cgr_noticias` ejecuta una fuente.

## Automatización

`.github/workflows/radar.yml` ejecuta el pipeline dos veces al día y también de forma manual. Instala dependencias, ejecuta tests, consulta fuentes, normaliza/deduplica, genera JSONL/Parquet/dashboard y hace commit solo si existen cambios, con `pull --rebase` antes del push.

## GitHub Pages

El sitio está en `docs/`. `pages.yml` despliega esa carpeta. En un repositorio nuevo puede ser necesario seleccionar una vez **Settings > Pages > Source: GitHub Actions**.

## Próximas especializaciones

- Conector exhaustivo al buscador CGR.
- Parser de Fiscalizaciones en Curso y estado `WATCH -> FINDING`.
- Taxonomía FAU computable.
- Tribunal de Cuentas y escalamiento de enforcement.
- Lectura de PDF cuando el HTML sea insuficiente.
- NER y resolución de entidades.
- DuckDB-WASM para SQL en navegador.
- Contrato común para integración con otros módulos AML.
