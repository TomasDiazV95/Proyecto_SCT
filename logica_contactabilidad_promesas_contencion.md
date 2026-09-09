# Definición de lógica — Contactabilidad, Promesas y Contención

## 1. Universo base

La tabla base del análisis será:

```sql
dbo.contencion_itau_vencida
```

Esta tabla define el universo de casos/RUT que se deben considerar en el dashboard.

La lógica general será:

```text
CONTENCION
   │
   │ Universo base de RUT
   │
   ├──── LEFT JOIN por RUT ──── GESTIONES
   │
   └──── LEFT JOIN por RUT ──── COMPROMISOS
```

Esto significa que:

- `contencion_itau_vencida` define el universo.
- `tmp_GEST_CRM` complementa la información de contacto.
- `tmp_FECHA_COMPROMISO_CRM` complementa la información de promesas.
- El cruce entre las tres fuentes se realiza por `RUT`.
- Un RUT que exista en gestiones o compromisos, pero no exista en contención, no debe ingresar al cálculo.

---

## 2. Total de casos

El total corresponde a los RUT únicos de la tabla de contención.

```text
TOTAL =
COUNT(DISTINCT RUT)
de contencion_itau_vencida
```

Siempre considerando los filtros activos del dashboard.

Para la vista Itaú Vencida:

```text
GESTOR = PHOENIX
```

Este `TOTAL` será el denominador de los indicadores de contacto.

---

## 3. Cruce con gestiones

Las gestiones se obtienen desde:

```sql
dbo.tmp_GEST_CRM
```

Filtrando:

```sql
cartera = 523
```

y el período correspondiente.

El cruce será:

```text
contencion_itau_vencida.RUT
=
tmp_GEST_CRM.RUT
```

Antes de calcular los porcentajes, las gestiones deben consolidarse a nivel de RUT para evitar duplicar casos.

---

## 4. Clasificación del estado de contacto

Un mismo RUT puede tener múltiples gestiones durante el mes.

Ejemplo:

```text
RUT 123
- SIN CONTACTO
- TERCERO
- TITULAR
```

Para evitar que un mismo cliente aparezca en más de una categoría, se debe aplicar la siguiente prioridad:

```text
TITULAR
   ↓
TERCERO
   ↓
SIN CONTACTO
```

La clasificación final por RUT será:

```text
Si tuvo al menos una gestión TITULAR
→ TITULAR

Si nunca tuvo TITULAR,
pero tuvo al menos una gestión TERCERO
→ TERCERO

Si tuvo gestiones,
pero ninguna fue TITULAR ni TERCERO
→ SIN CONTACTO
```

Por lo tanto, las categorías son mutuamente excluyentes.

---

## 5. Casos Titular

Corresponde a RUT únicos del universo de contención que, durante el período, tengan al menos una gestión clasificada como:

```text
TITULAR
```

Fórmula:

```text
% Titular =
Casos Titular
/
Total Casos
```

Ejemplo:

```text
Total Casos     = 1.000
Casos Titular   =   400

% Titular = 400 / 1.000 = 40%
```

---

## 6. Casos Tercero

Corresponde a RUT únicos del universo que:

```text
NO tengan ninguna gestión TITULAR
```

pero sí tengan al menos una gestión clasificada como:

```text
TERCERO
```

Fórmula:

```text
% Tercero =
Casos Tercero
/
Total Casos
```

Ejemplo:

```text
Total Casos     = 1.000
Casos Tercero   =   250

% Tercero = 250 / 1.000 = 25%
```

---

## 7. Casos Sin Contacto

Corresponde a RUT únicos que tengan gestión, pero cuyas gestiones no correspondan ni a:

```text
TITULAR
```

ni a:

```text
TERCERO
```

Regla:

```text
CONTACTOGESTION = TITULAR
→ Titular

CONTACTOGESTION = TERCERO
→ Tercero

Cualquier otro CONTACTOGESTION
→ Sin Contacto
```

Siempre respetando la prioridad:

```text
TITULAR > TERCERO > SIN CONTACTO
```

Fórmula:

```text
% Sin Contacto =
Casos Sin Contacto
/
Total Casos
```

---

## 8. Cruce con compromisos

Los compromisos se obtienen desde:

```sql
dbo.tmp_FECHA_COMPROMISO_CRM
```

Filtrando:

```sql
cartera = 523
```

y el período correspondiente.

El cruce será:

```text
contencion_itau_vencida.RUT
=
tmp_FECHA_COMPROMISO_CRM.RUT
```

---

## 9. Casos con Promesa

Un caso tiene promesa cuando el RUT posee una:

```text
FechaCompromiso
```

informada.

La definición será:

```text
CASO CON PROMESA =
RUT del universo de contención
que tiene al menos un registro
con FechaCompromiso informada
en tmp_FECHA_COMPROMISO_CRM.
```

Si un mismo cliente tiene varias promesas:

```text
RUT 123
FechaCompromiso 05-09-2026
FechaCompromiso 10-09-2026
FechaCompromiso 15-09-2026
```

debe contar una sola vez:

```text
Casos con Promesa = 1
```

porque el indicador mide casos, no cantidad de registros de promesa.

---

## 10. % Promesa

La fórmula será:

```text
% Promesa =
Casos con Promesa
/
Total Casos
```

Ejemplo:

```text
Total Casos        = 1.000
Casos con Promesa  =   180

% Promesa = 180 / 1.000 = 18%
```

---

## 11. Promesas Cumplidas

Las Promesas Cumplidas son un subconjunto de los Casos con Promesa.

Primero se identifica el universo:

```text
RUT con FechaCompromiso
```

Luego se revisa si ese mismo RUT tiene:

```text
CONTENCION > 0
```

en `contencion_itau_vencida`.

La regla definitiva será:

```text
PROMESA CUMPLIDA =
Tiene Promesa
AND
CONTENCION > 0
```

Ejemplos:

```text
Promesa = SI
CONTENCION = 0
→ Promesa No Cumplida
```

```text
Promesa = SI
CONTENCION > 0
→ Promesa Cumplida
```

---

## 12. % Promesa Cumplida

La fórmula será:

```text
% Promesa Cumplida =
Promesas Cumplidas
/
Casos con Promesa
```

Ejemplo:

```text
Casos con Promesa     = 180
Promesas Cumplidas    = 120

% Promesa Cumplida = 120 / 180 = 66,67%
```

---

## 13. Resumen de indicadores

| Indicador | Numerador | Denominador |
|---|---:|---:|
| % Titular | RUT clasificados como Titular | Total RUT de Contención |
| % Tercero | RUT clasificados como Tercero | Total RUT de Contención |
| % Sin Contacto | RUT clasificados como Sin Contacto | Total RUT de Contención |
| % Promesa | RUT con FechaCompromiso | Total RUT de Contención |
| % Promesa Cumplida | RUT con Promesa y `CONTENCION > 0` | RUT con Promesa |

---

## 14. Estructura conceptual

```text
CONTENCIÓN
Universo base por RUT
        │
        ├──────── GESTIONES
        │            │
        │            ├─ ¿Tuvo TITULAR?
        │            │       → TITULAR
        │            │
        │            ├─ No Titular, pero tuvo TERCERO
        │            │       → TERCERO
        │            │
        │            └─ Tuvo gestión, pero no Titular ni Tercero
        │                    → SIN CONTACTO
        │
        └──────── COMPROMISOS
                     │
                     ├─ FechaCompromiso informada
                     │       → CASO CON PROMESA
                     │
                     └─ Caso con Promesa
                         + CONTENCION > 0
                         → PROMESA CUMPLIDA
```

---

## 15. Estructura recomendada por RUT

Antes de realizar cualquier suma o porcentaje, se recomienda construir una base consolidada con una sola fila por RUT.

Ejemplo:

| RUT | ES_TITULAR | ES_TERCERO | ES_SIN_CONTACTO | TIENE_PROMESA | PROMESA_CUMPLIDA |
|---|---:|---:|---:|---:|---:|
| 11111111-1 | 1 | 0 | 0 | 1 | 1 |
| 22222222-2 | 0 | 1 | 0 | 1 | 0 |
| 33333333-3 | 0 | 0 | 1 | 0 | 0 |

De esta forma, posteriormente los indicadores se calculan mediante sumas simples:

```text
Casos Titular = SUM(ES_TITULAR)
Casos Tercero = SUM(ES_TERCERO)
Casos Sin Contacto = SUM(ES_SIN_CONTACTO)
Casos con Promesa = SUM(TIENE_PROMESA)
Promesas Cumplidas = SUM(PROMESA_CUMPLIDA)
```

---

## 16. Regla final

La lógica definitiva del módulo será:

```text
CONTENCION
=
Universo base
```

```text
GESTIONES
=
Clasificación de contacto por RUT
```

```text
COMPROMISOS
=
Identificación de casos con promesa
```

```text
PROMESA CUMPLIDA
=
Caso con Promesa
+
CONTENCION > 0
```

Todos los cálculos deben realizarse a nivel de RUT único, evitando duplicaciones por múltiples gestiones o múltiples compromisos.
