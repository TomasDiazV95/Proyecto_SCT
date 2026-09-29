# KPI Operacional — Plan y Maqueta

## 1. Objetivo

Construir un **KPI Operacional** que permita analizar el desempeño de las distintas carteras y mandantes en un período determinado.

El panel debe permitir responder rápidamente:

- ¿Cuántos casos tengo asignados?
- ¿Cuál es el saldo total asignado?
- ¿Qué nivel de contactabilidad estoy logrando?
- ¿Cuánto estoy recuperando en pagos?
- ¿Qué tipos de contacto estoy obteniendo?
- ¿Cuántos compromisos se generan?
- ¿Cuántos compromisos se cumplen?
- ¿Cuántos compromisos se incumplen?

---

## 2. Filtros generales

Todos los indicadores y gráficos deben responder a los mismos filtros:

- **Período**
- **Mandante**
- **Cartera**
- **Tramo de mora**
- **Producto**

Ejemplo:

```text
Período: Septiembre 2026
Mandante: Itaú
Cartera: Vencida
Tramo Mora: 31-60
Producto: Consumo
```

El filtro **Período** es obligatorio, ya que las asignaciones y pagos se actualizan mensualmente.

---

## 3. KPIs principales

La primera sección del dashboard debe mostrar las métricas más importantes.

### 3.1 Asignación

Cantidad de clientes o casos asignados.

Recomendación:

```text
Casos asignados = COUNT DISTINCT RUT
```

Ejemplo:

```text
12.450 casos
```

También se puede mostrar de forma secundaria la cantidad de operaciones.

---

### 3.2 Saldo asignado

Monto total asignado.

```text
Saldo asignado = SUM(saldo_asignado)
```

Mostrar en millones:

```text
$8.540 MM
```

---

### 3.3 Contactabilidad

Porcentaje de clientes gestionados con contacto directo.

```text
Contactabilidad =
RUT con contacto directo
-------------------------
RUT gestionados
```

Ejemplo:

```text
1.752 RUT con contacto directo
4.000 RUT gestionados

Contactabilidad = 43,8%
```

La contactabilidad debe calcularse por **RUT único** y no por cantidad de gestiones.

---

### 3.4 Pagos

Monto total recuperado.

```text
Pagos = SUM(monto_pago)
```

Ejemplo:

```text
$485 MM
```

También se recomienda mostrar:

```text
% Recuperación =
Pagos
----------------
Saldo asignado
```

Ejemplo:

```text
Recuperación: 5,7%
```

---

## 4. KPIs complementarios

Además de los KPIs solicitados, se recomienda incluir:

### Cobertura

Mide cuánto de la cartera asignada fue efectivamente gestionada.

```text
Cobertura =
RUT gestionados
----------------
RUT asignados
```

### Contactabilidad sobre asignación

```text
Contacto sobre asignación =
RUT contacto directo
----------------------
RUT asignados
```

Esto permite diferenciar una cartera con buena contactabilidad pero baja cobertura.

---

# 5. Maqueta general

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ KPI OPERACIONAL                                              SEP 2026       │
│                                                                              │
│ Mandante [Todos ▼] Cartera [Todas ▼] Tramo [Todos ▼] Producto [Todos ▼]    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ASIGNACIÓN       SALDO ASIGNADO      CONTACTABILIDAD       PAGOS            │
│ 12.450           $8.540 MM           43,8%                 $485 MM           │
│                                                           Recup. 5,7%        │
│                                                                              │
├─────────────────────────────────────┬────────────────────────────────────────┤
│ ASIGNACIÓN POR TRAMO                │ SALDO ASIGNADO POR TRAMO               │
│                                     │                                        │
│ 0-30    ███████████ 4.250           │ 0-30    ███████████ $2.100 MM          │
│ 31-60   ████████    3.200           │ 31-60   █████████   $1.850 MM          │
│ 61-90   █████       2.150           │ 61-90   ████████    $1.700 MM          │
├─────────────────────────────────────┼────────────────────────────────────────┤
│ TIPOS DE CONTACTO                   │ PAGOS / RECUPERACIÓN                   │
│                                     │                                        │
│ Directo       44%                   │ 0-30        $185 MM    8,8%            │
│ Indirecto     18%                   │ 31-60       $120 MM    6,5%            │
│ Sin contacto  38%                   │ 61-90        $85 MM    5,0%            │
├──────────────────────────────────────────────────────────────────────────────┤
│ COMPROMISOS                                                                  │
│                                                                              │
│ TOTAL               CUMPLIDOS             INCUMPLIDOS       % CUMPLIMIENTO  │
│ 1.480               920                    560               62,2%            │
├─────────────────────────────────────┬────────────────────────────────────────┤
│ EVOLUCIÓN CONTACTABILIDAD           │ EVOLUCIÓN RECUPERACIÓN                 │
│                                     │                                        │
│ Tendencia diaria / mensual          │ Tendencia diaria / mensual             │
└─────────────────────────────────────┴────────────────────────────────────────┘
```

---

# 6. Gráficos de asignación

## 6.1 Casos asignados por tramo de mora

Gráfico recomendado: **barras horizontales**.

Ejemplo:

```text
CASOS ASIGNADOS POR TRAMO

0-30      ████████████████████  4.250
31-60     ███████████████       3.200
61-90     ██████████            2.150
91-120    ██████                1.300
120+      ███████               1.550
```

Este gráfico permite visualizar dónde está concentrado el volumen de clientes.

---

## 6.2 Saldo asignado por tramo

```text
SALDO ASIGNADO POR TRAMO

0-30       $2.100 MM
31-60      $1.850 MM
61-90      $1.700 MM
91-120     $1.140 MM
120+       $1.750 MM
```

Permite diferenciar entre:

- alto volumen de clientes y bajo saldo;
- bajo volumen de clientes y alto saldo.

---

# 7. Contactabilidad

## 7.1 Tipos de contacto

Clasificar las gestiones en tres grandes grupos:

| Tipo | Ejemplos |
|---|---|
| **Directo** | Titular, deudor |
| **Indirecto** | Familiar, tercero, recado |
| **Sin contacto** | No contesta, apagado, buzón, teléfono inválido |

La distribución debe sumar siempre:

```text
Directo + Indirecto + Sin contacto = 100%
```

Ejemplo:

```text
Contacto directo       44%
Contacto indirecto     18%
Sin contacto           38%
```

Gráfico recomendado:

- barra 100%;
- donut;
- barras horizontales.

---

## 7.2 Regla de cálculo

Se recomienda definir el tipo de contacto a nivel de **RUT**.

Ejemplo de prioridad:

```text
Si el RUT tuvo al menos un contacto directo:
    Directo

Si no tuvo contacto directo pero sí indirecto:
    Indirecto

Si no tuvo contacto directo ni indirecto:
    Sin contacto
```

Esto evita duplicar clientes por múltiples gestiones.

---

# 8. Pagos y recuperación

## 8.1 Pagos por tramo de mora

```text
PAGOS RECUPERADOS

0-30       $185 MM
31-60      $120 MM
61-90       $85 MM
91-120      $45 MM
120+        $50 MM
```

---

## 8.2 Recuperación porcentual

```text
RECUPERACIÓN SOBRE SALDO

0-30       8,8%
31-60      6,5%
61-90      5,0%
91-120     3,9%
120+       2,9%
```

Fórmula:

```text
% Recuperación =
Monto pagado
-------------
Saldo asignado
```

---

# 9. Compromisos

Mostrar los siguientes indicadores:

### Compromisos totales

```text
COUNT(compromisos)
```

### Compromisos cumplidos

Compromisos cuya condición de pago fue cumplida.

### Compromisos incumplidos

Compromisos cuya fecha ya venció y no cumplen la condición establecida.

### Cumplimiento de compromisos

```text
% Cumplimiento =
Compromisos cumplidos
----------------------
Compromisos vencidos
```

No se deben considerar compromisos futuros como incumplidos.

---

## 9.1 Maqueta de compromisos

```text
┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ COMPROMISOS        │ │ CUMPLIDOS          │ │ INCUMPLIDOS        │
│                    │ │                    │ │                    │
│ 1.480              │ │ 920                │ │ 560                │
│                    │ │ 62,2%              │ │ 37,8%              │
└────────────────────┘ └────────────────────┘ └────────────────────┘
```

---

# 10. Evolución temporal

Agregar gráficos de línea para analizar tendencias.

## Evolución de contactabilidad

```text
01 Sep    38%
05 Sep    40%
10 Sep    41%
15 Sep    43%
20 Sep    44%
25 Sep    46%
```

## Evolución de pagos

Mostrar:

- pagos diarios;
- pagos acumulados;
- recuperación acumulada.

## Evolución de compromisos

Mostrar:

- compromisos generados;
- compromisos vencidos;
- compromisos cumplidos;
- porcentaje de cumplimiento.

---

# 11. Estructura de datos recomendada

Actualmente las asignaciones y pagos están separados por mandante.

La recomendación es crear una capa homologada.

---

## 11.1 Vista de asignaciones

```text
vw_kpi_asignacion
```

Columnas mínimas:

```text
periodo
mandante
cartera
rut
operacion
producto
tramo_mora
saldo_asignado
```

Origen:

```text
Tabla asignación Itaú
Tabla asignación Banco Internacional
Tabla asignación Santander
Tabla asignación Tanner
...
```

Todas deben convertirse al mismo formato.

---

## 11.2 Vista de pagos

```text
vw_kpi_pagos
```

Columnas:

```text
periodo
fecha_pago
mandante
cartera
rut
operacion
producto
monto_pago
```

---

## 11.3 Vista de gestiones

Unificar CRM 2.0 y CRM 3.0.

```text
vw_kpi_gestiones
```

Columnas:

```text
fecha_gestion
periodo
mandante
cartera
rut
operacion
producto
tramo_mora
tipo_contacto
ejecutivo
```

---

## 11.4 Vista de compromisos

```text
vw_kpi_compromisos
```

Columnas:

```text
periodo
mandante
cartera
rut
operacion
fecha_compromiso
fecha_vencimiento
monto_compromiso
estado_compromiso
monto_pagado
```

---

# 12. Relación entre las fuentes

Las principales llaves de relación deberían ser:

```text
PERIODO
MANDANTE
CARTERA
RUT
```

Cuando corresponda:

```text
OPERACION
```

Modelo conceptual:

```text
                    DIM_PERIODO
                         │
                    DIM_MANDANTE
                         │
                     DIM_CARTERA
                         │
                     DIM_PRODUCTO
                         │
                    DIM_TRAMO_MORA
                         │
            ┌────────────┼──────────────┐
            │            │              │
            ▼            ▼              ▼
      ASIGNACIONES    GESTIONES       PAGOS
            │            │              │
            └────────────┼──────────────┘
                         │
                         ▼
                   COMPROMISOS
```

---

# 13. Definición oficial de KPIs

| KPI | Fórmula |
|---|---|
| Casos asignados | `COUNT DISTINCT RUT asignado` |
| Saldo asignado | `SUM(saldo_asignado)` |
| Clientes gestionados | `COUNT DISTINCT RUT gestionado` |
| Contacto directo | `COUNT DISTINCT RUT contacto directo` |
| Contactabilidad | `RUT contacto directo / RUT gestionados` |
| Cobertura | `RUT gestionados / RUT asignados` |
| Contactabilidad sobre asignación | `RUT contacto directo / RUT asignados` |
| Pagos | `SUM(monto_pago)` |
| Recuperación | `Pagos / Saldo asignado` |
| Compromisos | `COUNT(compromisos)` |
| Compromisos cumplidos | `COUNT(compromisos cumplidos)` |
| Compromisos incumplidos | `COUNT(compromisos vencidos incumplidos)` |
| Cumplimiento compromisos | `Cumplidos / Compromisos vencidos` |

---

# 14. Plan de construcción

## Etapa 1 — Homologación de datos

1. Identificar tablas de asignación por mandante.
2. Homologar nombres de columnas.
3. Identificar tablas de pagos por mandante.
4. Homologar pagos.
5. Definir relación entre mandante, cartera, RUT y operación.

---

## Etapa 2 — Gestiones

1. Integrar CRM 2.0.
2. Integrar CRM 3.0.
3. Crear una tabla o vista común.
4. Homologar estados de contacto.
5. Clasificar:

```text
Directo
Indirecto
Sin contacto
```

---

## Etapa 3 — Compromisos

1. Identificar compromisos generados.
2. Definir fecha de vencimiento.
3. Cruzar compromisos con pagos.
4. Crear estado:

```text
Pendiente
Cumplido
Incumplido
```

---

## Etapa 4 — Vistas SQL

Crear:

```text
vw_kpi_asignacion
vw_kpi_pagos
vw_kpi_gestiones
vw_kpi_compromisos
```

---

## Etapa 5 — Backend / API

La API debe recibir como parámetros:

```text
periodo
mandante
cartera
tramo_mora
producto
```

Ejemplo:

```text
/api/kpi-operacional/resumen
/api/kpi-operacional/asignacion
/api/kpi-operacional/contactabilidad
/api/kpi-operacional/pagos
/api/kpi-operacional/compromisos
/api/kpi-operacional/evolucion
```

---

## Etapa 6 — Frontend

Orden recomendado:

1. Filtros.
2. Cards principales.
3. Asignación por tramo.
4. Saldo por tramo.
5. Tipos de contacto.
6. Pagos y recuperación.
7. Compromisos.
8. Evolución temporal.

---

# 15. Reglas que deben quedar definidas antes de desarrollar

Antes de comenzar el desarrollo hay que cerrar estas definiciones:

### ¿Qué es un caso?

Recomendación:

```text
Caso = RUT único
```

Pero puede utilizarse operación si el negocio necesita ese nivel.

### ¿Qué pago pertenece a qué asignación?

Definir prioridad:

```text
Mandante + Cartera + Período + RUT + Operación
```

o, si no existe operación:

```text
Mandante + Cartera + Período + RUT
```

### ¿Qué tipo de contacto tiene un RUT?

Recomendación:

```text
Directo > Indirecto > Sin contacto
```

Es decir, si durante el período un cliente tuvo al menos un contacto directo, se clasifica como directo.

---

# 16. Resultado esperado

El KPI Operacional debe permitir responder rápidamente:

- cuánto inventario existe;
- cuánto saldo representa;
- cuánto de la cartera se está trabajando;
- cuánto contacto directo se obtiene;
- cómo se distribuyen los tipos de contacto;
- cuánto dinero se recupera;
- qué porcentaje del saldo se recupera;
- cuántos compromisos se generan;
- qué porcentaje de compromisos se cumple;
- qué mandantes, carteras, productos y tramos muestran diferencias operacionales.

El objetivo final es tener una **visión operacional única y comparable entre todos los mandantes y carteras**.
