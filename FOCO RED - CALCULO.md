# FOCO RED (Santander Hipotecario): cómo se calcula el % de cumplimiento

## 1. Fuente de datos

- Archivo mensual **CIERRE FOCO \<MES\>.xlsx**, hoja **BASE FOCO**. Tiene una fila por caso (RUT / operación) con su estrategia, el resultado de la gestión y el ejecutivo.
- El resultado de cada caso (columna `TIPO GESTION`) viene del CRM (hoja GESTION FOCO). Es la mejor gestión del mes, en este orden de prioridad: compromiso de pago > contacto titular > contacto tercero > sin contacto > sin gestión.
- El ejecutivo del caso es la columna `Usuario` de la BASE FOCO. Los casos que dicen "Dinamico" (discador y gestiones de ejecutivos fuera del equipo) no se reasignan.

## 2. Universo

Solo entran los casos de las 3 estrategias del foco hipotecario:

| Estrategia | Casos (oct-2026) |
|---|---|
| Reorganizate | 635 |
| Salida 1: Reestr. Hipotecaria | 5.519 |
| Salida 2: Nuevo Hipotecario | 1.338 |
| **Total** | **7.492** |

"Flujo Consumo moroso" y "Flujo Consumo moroso Sep" **no** entran.

## 3. Definiciones

| Concepto | Qué cuenta |
|---|---|
| **Casos** | Casos del foco a nombre del ejecutivo (o de la estrategia) |
| **Contactados** | Casos con resultado **CON COMPROMISO DE PAGO** o **CONTACTO TITULAR**. El contacto con un tercero no cuenta. |
| **Compromisos** | Casos con resultado **CON COMPROMISO DE PAGO** (los "interesados") |

## 4. Cumplimiento por ejecutivo

Ejecutivos que se miden (los que tienen casos a su nombre en la BASE FOCO):
Constanza Acevedo, Dylan Petit-Laurent, Marisol Alvarez, Matilda Guzman, Richard Boulett, Victoria Sobrino, Violeta Zubicueta y Yury Monsalve.

Francisca Huerta, Marcela Roca, Rina Valbuena y Antonia Vidal **no van** en esta tabla porque su cumplimiento es grupal.

### Fórmulas

| Indicador | Fórmula | Meta |
|---|---|---|
| **%CONT.** | contactados del ejecutivo / contactados de **todos** los ejecutivos de la tabla | 55% |
| **%COMPR.** | compromisos del ejecutivo / contactados **del mismo ejecutivo** | 45% |
| **%CUMPL. contacto** | %CONT. / 55% | sin tope |
| **%CUMPL. compromiso** | %COMPR. / 45% | sin tope |
| **% FINAL** | 50% × %CUMPL. contacto + 50% × %CUMPL. compromiso | sin tope |

- %CONT. mide qué parte de los contactos del equipo hizo cada ejecutivo.
- %COMPR. mide cuántos de sus contactos terminaron en compromiso.
- Ningún cumplimiento tiene tope.

### Ejemplo: Constanza Acevedo (octubre 2026)

| Paso | Cálculo | Resultado |
|---|---|---|
| Contactados | 164 compromisos + 2 contactos titular | 166 |
| %CONT. | 166 / 1.653 | 10,04% |
| %CUMPL. contacto | 10,04% / 55% | 18% |
| %COMPR. | 164 / 166 | 98,80% |
| %CUMPL. compromiso | 98,80% / 45% | 220% |
| **% FINAL** | 50% × 18% + 50% × 220% | **119%** |

### Resultado octubre 2026

| Ejecutivo | Contactados | %CONT. | Compromisos | %COMPR. | % FINAL |
|---|---|---|---|---|---|
| Constanza Acevedo | 166 | 10,04% | 164 | 98,80% | 119% |
| Dylan Petit-Laurent | 204 | 12,34% | 196 | 96,08% | 118% |
| Marisol Alvarez | 247 | 14,94% | 240 | 97,17% | 122% |
| Matilda Guzman | 169 | 10,22% | 158 | 93,49% | 113% |
| Richard Boulett | 180 | 10,89% | 180 | 100,00% | 121% |
| Victoria Sobrino | 305 | 18,45% | 293 | 96,07% | 124% |
| Violeta Zubicueta | 180 | 10,89% | 176 | 97,78% | 119% |
| Yury Monsalve | 202 | 12,22% | 196 | 97,03% | 119% |
| **Total** | **1.653** | 100% | **1.603** | 96,98% | — |

La fila TOTAL de esta tabla no sirve como cumplimiento del equipo. Su %CONT. siempre es 100%, porque es el total dividido por sí mismo.

## 5. Cumplimiento por estrategia (cartera completa)

Mide toda la cartera foco, incluidos los casos "Dinamico". Aquí los % son sobre los **casos cargados**:

| Indicador | Fórmula | Meta |
|---|---|---|
| **%CONT.** | contactados / casos cargados | 55% |
| **%COMPR.** | compromisos / casos cargados | 45% |
| **% FINAL** | 50% × (%CONT. / 55%) + 50% × (%COMPR. / 45%) | sin tope |

| Estrategia | Casos | Contactados | %CONT. | Compromisos | %COMPR. | % FINAL |
|---|---|---|---|---|---|---|
| Reorganizate | 635 | 330 | 51,97% | 277 | 43,62% | 96% |
| Salida 1: Reestr. Hipotecaria | 5.519 | 3.019 | 54,70% | 2.531 | 45,86% | 101% |
| Salida 2: Nuevo Hipotecario | 1.338 | 775 | 57,92% | 643 | 48,06% | 106% |
| **Total** | **7.492** | **4.124** | 55,05% | **3.451** | 46,06% | **101%** |

## 6. Excel FOCO RED

- **Hoja FOCO RED:** arriba, la tabla por ejecutivo; abajo, el detalle por estrategia. Los % son fórmulas que cuentan sobre la hoja de detalle. Las metas y las ponderaciones (celdas celestes) se pueden cambiar a mano.
- **Hoja DETALLE FOCO:** un caso por fila, con RUT, operación, estrategia, ciclo, deuda, usuario, resultado, si fue contactado, si tiene compromiso y el nombre del ejecutivo.

## 7. Notas de octubre 2026

- Las gestiones del CRM incluidas en el archivo llegan hasta el **29-10-2026**. Faltan el 30 y el 31.
