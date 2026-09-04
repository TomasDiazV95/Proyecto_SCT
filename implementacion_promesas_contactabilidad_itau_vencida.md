# Implementación — Promesas y Promesas Cumplidas
## Módulo Contactabilidad Itaú Vencida

Este documento complementa el requerimiento funcional y técnico del módulo **Contactabilidad Itaú Vencida**.

El objetivo es incorporar al **Tubo de Contactabilidad por Gestor** los siguientes indicadores:

| Indicador |
|---|
| Casos con Promesa |
| % Promesa |
| Promesas Cumplidas |
| % Promesa Cumplida |

La vista continuará trabajando únicamente con:

```text
Gestor = PHOENIX
Cartera CRM = 523
```

---

# 1. Regla de negocio

## 1.1 Casos con Promesa

La fuente oficial para identificar promesas será:

```sql
dbo.tmp_FECHA_COMPROMISO_CRM
```

Para Itaú Vencida se deben considerar únicamente registros con:

```sql
cartera = 523
```

y cuya `FechaGestion` se encuentre dentro del período consultado.

Ejemplo para septiembre 2026:

```sql
SELECT *
FROM dbo.tmp_FECHA_COMPROMISO_CRM
WHERE cartera = 523
  AND FechaGestion >= '2026-09-01'
  AND FechaGestion < '2026-10-01'
ORDER BY FechaCompromiso DESC;
```

> No utilizar `BETWEEN '2026-09-01' AND '2026-09-30'` si `FechaGestion` es `datetime`, porque podrían excluirse registros del último día que tengan hora. Debe usarse 'yyyy-mm-01' and fecha proceso

Un **Caso con Promesa** corresponde a un cliente/caso del universo filtrado que tenga al menos un registro válido en `tmp_FECHA_COMPROMISO_CRM` durante el período.

Si un mismo cliente tiene múltiples compromisos durante el mes, debe contar **una sola vez** para el indicador `Casos con Promesa`.

---

# 2. Promesas Cumplidas

Una **Promesa Cumplida** corresponde a un caso que:

1. Tiene promesa en `tmp_FECHA_COMPROMISO_CRM`.
2. Pertenece a `cartera = 523`.
3. Se encuentra dentro del período consultado.
4. Existe dentro del universo de Itaú Vencida filtrado para PHOENIX.
5. Tiene pago/contención mayor a cero en `contencion_itau_vencida`.

Regla:

```text
Promesa Cumplida =
Caso con Promesa
AND CONTENCION > 0
```

Por lo tanto:

```sql
CASE
    WHEN ISNULL(CONTENCION, 0) > 0 THEN 1
    ELSE 0
END
```

No se debe contar una fila de promesa varias veces si el cliente posee múltiples registros de compromiso.

---

# 3. Definición de los indicadores

## 3.1 Casos con Promesa

```text
Cantidad de clientes/casos únicos
con al menos una promesa válida durante el período.
```

Debe calcularse sobre el mismo universo utilizado por el resto del dashboard.

---

## 3.2 % Promesa

La fórmula será:

```text
% Promesa =
Casos con Promesa
/
Casos con Contacto Titular
```

Ejemplo:

```text
Casos con Contacto Titular = 1.000
Casos con Promesa          =   300

% Promesa = 300 / 1.000 = 30%
```

Si `Casos con Contacto Titular = 0`, devolver:

```text
0%
```

Nunca devolver:

```text
NaN
Infinity
NULL
```

---

## 3.3 Promesas Cumplidas

```text
Cantidad de casos con promesa
que además presentan CONTENCION > 0.
```

Ejemplo:

```text
Casos con Promesa = 300

De esos 300:
240 presentan CONTENCION > 0

Promesas Cumplidas = 240
```

---

## 3.4 % Promesa Cumplida

La fórmula será:

```text
% Promesa Cumplida =
Promesas Cumplidas
/
Casos con Promesa
```

Ejemplo:

```text
Promesas Cumplidas = 240
Casos con Promesa  = 300

% Promesa Cumplida = 240 / 300 = 80%
```

Si `Casos con Promesa = 0`, devolver:

```text
0%
```

---

# 4. Resultado esperado en Tubo de Contactabilidad

La tabla debe quedar de la siguiente forma:

| Gestor | Recurrencia Call + Terreno | Casos Asignados | Casos con Gestión | % Gestionado | Casos con Contacto Titular | % Contacto Titular | Casos con Promesa | % Promesa | Promesas Cumplidas | % Promesa Cumplida |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PHOENIX |  |  |  |  |  |  |  |  |  |  |

Fórmulas:

```text
% Gestionado =
Casos con Gestión / Casos Asignados
```

```text
% Contacto Titular =
Casos con Contacto Titular / Casos con Gestión
```

```text
% Promesa =
Casos con Promesa / Casos con Contacto Titular
```

```text
% Promesa Cumplida =
Promesas Cumplidas / Casos con Promesa
```

---

# 5. Fuente de cada indicador

| Indicador | Fuente | Regla principal |
|---|---|---|
| Casos Asignados | `asignacion_itau_vencida` | `COUNT(DISTINCT RUT)` según `FECHA_CARGA` |
| Casos con Gestión | `tmp_GEST_CRM` | Cliente/RUT con al menos una gestión válida, `cartera = 523` |
| Casos con Contacto Titular | `tmp_GEST_CRM` | `CONTACTOGESTION = 'TITULAR'`, `cartera = 523` |
| Casos con Promesa | `tmp_FECHA_COMPROMISO_CRM` | Al menos una promesa en el período, `cartera = 523` |
| Promesas Cumplidas | `tmp_FECHA_COMPROMISO_CRM` + `contencion_itau_vencida` | Caso con promesa y `CONTENCION > 0` |

---

# 6. Llave de cruce

Antes de implementar el JOIN se debe validar cuál es la llave real disponible en:

```text
tmp_FECHA_COMPROMISO_CRM
contencion_itau_vencida
asignacion_itau_vencida
tmp_GEST_CRM
```

La prioridad debe ser:

```text
1. Operación, si identifica inequívocamente el caso en todas las fuentes.
2. RUT + operación, si ambas columnas son necesarias.
3. RUT normalizado, cuando la lógica del dashboard esté definida a nivel cliente.
```

Para el Tubo actual, los indicadores deben quedar consolidados a nivel de **caso/cliente único**, evitando que múltiples filas de promesa multipliquen el resultado.

No hacer directamente:

```sql
contencion_itau_vencida
JOIN tmp_FECHA_COMPROMISO_CRM
```

sin agregar previamente la tabla de promesas.

---

# 7. Validación previa de `tmp_FECHA_COMPROMISO_CRM`

Antes del desarrollo ejecutar:

```sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'tmp_FECHA_COMPROMISO_CRM'
ORDER BY ORDINAL_POSITION;
```

También revisar una muestra:

```sql
SELECT TOP 100 *
FROM dbo.tmp_FECHA_COMPROMISO_CRM
WHERE cartera = 523
ORDER BY FechaGestion DESC;
```

Se debe identificar como mínimo:

```text
- columna RUT
- columna operación, si existe
- FechaGestion
- FechaCompromiso
- cartera
```

---

# 8. Validar duplicidad de promesas

Una misma persona puede tener más de una promesa durante el período.

Por lo tanto, primero se debe validar:

```sql
-- Ajustar RUT al nombre real de la columna
SELECT
    RUT,
    COUNT(*) AS cantidad_promesas
FROM dbo.tmp_FECHA_COMPROMISO_CRM
WHERE cartera = 523
  AND FechaGestion >= '2026-09-01'
  AND FechaGestion < '2026-10-01'
GROUP BY RUT
HAVING COUNT(*) > 1
ORDER BY cantidad_promesas DESC;
```

Esto es importante porque:

```text
3 filas de promesa del mismo RUT
NO deben significar
3 casos con promesa.
```

Para el Tubo:

```text
1 RUT con una o más promesas = 1 Caso con Promesa
```

---

# 9. CTE recomendada para Promesas

El backend debe reducir primero la tabla de compromisos a una fila por cliente/caso.

Ejemplo conceptual:

```sql
WITH PROMESAS AS (
    SELECT
        RUT,
        MAX(FechaGestion) AS UltimaFechaGestionPromesa,
        MAX(FechaCompromiso) AS UltimaFechaCompromiso
    FROM dbo.tmp_FECHA_COMPROMISO_CRM
    WHERE cartera = 523
      AND FechaGestion >= @fecha_inicio
      AND FechaGestion < @fecha_fin
    GROUP BY RUT
)
SELECT *
FROM PROMESAS;
```

> Reemplazar `RUT` por la columna real identificada durante el levantamiento.

Esta CTE debe representar:

```text
1 fila por cliente con promesa
```

---

# 10. CTE recomendada para Contención

La fuente de pago continúa siendo:

```sql
dbo.contencion_itau_vencida
```

Para evitar duplicidad, primero consolidar la información por la llave definida.

Ejemplo conceptual a nivel RUT:

```sql
WITH CONTENCION AS (
    SELECT
        RUT,
        SUM(ISNULL(CONTENCION, 0)) AS MONTO_CONTENCION
    FROM dbo.contencion_itau_vencida
    WHERE GESTOR = 'PHOENIX'
    GROUP BY RUT
)
SELECT *
FROM CONTENCION;
```

La regla de cumplimiento será:

```sql
CASE
    WHEN MONTO_CONTENCION > 0 THEN 1
    ELSE 0
END AS PROMESA_CUMPLIDA
```

Si negocio determina que `CONTENCION` ya viene consolidada por caso y no corresponde sumar filas, se debe utilizar una agregación equivalente que preserve la regla:

```text
Existe al menos un CONTENCION > 0.
```

Ejemplo:

```sql
MAX(
    CASE
        WHEN ISNULL(CONTENCION, 0) > 0 THEN 1
        ELSE 0
    END
)
```

---

# 11. Query conceptual completa

La consulta productiva debe reutilizar el universo que ya utiliza el dashboard.

Ejemplo conceptual:

```sql
WITH UNIVERSO AS (
    SELECT DISTINCT
        RUT
    FROM dbo.asignacion_itau_vencida
    WHERE FECHA_CARGA = @fecha_proceso
),

ATRIBUTOS AS (
    SELECT
        RUT,
        MAX(
            CASE
                WHEN ISNULL(CONTENCION, 0) > 0 THEN 1
                ELSE 0
            END
        ) AS TIENE_CONTENCION
    FROM dbo.contencion_itau_vencida
    WHERE GESTOR = 'PHOENIX'
    GROUP BY RUT
),

GESTIONES AS (
    SELECT
        RUT,
        MAX(
            CASE
                WHEN CONTACTOGESTION = 'TITULAR' THEN 1
                ELSE 0
            END
        ) AS TIENE_CONTACTO_TITULAR
    FROM dbo.tmp_GEST_CRM
    WHERE cartera = 523
      AND GestionFecha >= @fecha_inicio
      AND GestionFecha < @fecha_fin
    GROUP BY RUT
),

PROMESAS AS (
    SELECT
        RUT,
        1 AS TIENE_PROMESA,
        MAX(FechaGestion) AS ULTIMA_FECHA_GESTION_PROMESA,
        MAX(FechaCompromiso) AS ULTIMA_FECHA_COMPROMISO
    FROM dbo.tmp_FECHA_COMPROMISO_CRM
    WHERE cartera = 523
      AND FechaGestion >= @fecha_inicio
      AND FechaGestion < @fecha_fin
    GROUP BY RUT
),

BASE AS (
    SELECT
        U.RUT,
        ISNULL(G.TIENE_CONTACTO_TITULAR, 0) AS TIENE_CONTACTO_TITULAR,
        ISNULL(P.TIENE_PROMESA, 0) AS TIENE_PROMESA,
        ISNULL(A.TIENE_CONTENCION, 0) AS TIENE_CONTENCION,
        CASE
            WHEN ISNULL(P.TIENE_PROMESA, 0) = 1
             AND ISNULL(A.TIENE_CONTENCION, 0) = 1
            THEN 1
            ELSE 0
        END AS PROMESA_CUMPLIDA
    FROM UNIVERSO U
    LEFT JOIN GESTIONES G
        ON U.RUT = G.RUT
    LEFT JOIN PROMESAS P
        ON U.RUT = P.RUT
    LEFT JOIN ATRIBUTOS A
        ON U.RUT = A.RUT
)

SELECT
    COUNT(*) AS CASOS_ASIGNADOS,

    SUM(TIENE_CONTACTO_TITULAR) AS CASOS_CONTACTO_TITULAR,

    SUM(TIENE_PROMESA) AS CASOS_PROMESA,

    CAST(
        100.0 * SUM(TIENE_PROMESA)
        / NULLIF(SUM(TIENE_CONTACTO_TITULAR), 0)
        AS DECIMAL(10,2)
    ) AS PORCENTAJE_PROMESA,

    SUM(PROMESA_CUMPLIDA) AS PROMESAS_CUMPLIDAS,

    CAST(
        100.0 * SUM(PROMESA_CUMPLIDA)
        / NULLIF(SUM(TIENE_PROMESA), 0)
        AS DECIMAL(10,2)
    ) AS PORCENTAJE_PROMESA_CUMPLIDA

FROM BASE;
```

## Importante

La query anterior es una guía de estructura.

Antes de copiarla a producción se debe reemplazar:

```text
RUT
```

por la llave real confirmada en `tmp_FECHA_COMPROMISO_CRM`.

También se debe integrar con la query agregada que ya construye:

```text
Casos Asignados
Casos con Gestión
% Gestionado
Casos con Contacto Titular
% Contacto Titular
Recurrencia
```

No crear otra consulta completa e independiente si se puede incorporar `PROMESAS` a la agregación existente.

---

# 12. Regla de filtros

Los indicadores de Promesa deben responder exactamente a los mismos filtros del Tubo.

Esto significa:

```text
Período
Fecha hasta
Gestor = PHOENIX
Canal
Segmento
Fase
Producto
Tipo Campaña
Detalle Marca
Estado Contención
Estado Contacto
```

La secuencia correcta es:

```text
1. Construir universo filtrado.
2. Obtener RUT/casos que pertenecen a ese universo.
3. Buscar sus promesas.
4. Calcular promesas cumplidas.
5. Agregar indicadores.
```

No se deben calcular primero todas las promesas de cartera 523 y aplicar filtros comerciales después de forma parcial.

---

# 13. Fecha hasta

Si la pantalla permite seleccionar una `fecha_hasta`, las promesas también deben respetar ese corte.

Ejemplo:

```text
Período:    septiembre 2026
Fecha hasta: 15-09-2026
```

Promesas válidas:

```sql
FechaGestion >= '2026-09-01'
AND FechaGestion < '2026-09-16'
```

No incluir promesas registradas después del día seleccionado.

La `FechaCompromiso` puede ser posterior a `fecha_hasta`; para identificar que el caso tiene promesa, la fecha que controla la inclusión mensual será `FechaGestion`, según la regla definida.

---

# 14. Backend

Se debe ampliar el endpoint existente:

```http
GET /api/contactabilidad/itau-vencida/tubo
```

La respuesta debe incorporar:

```json
{
  "gestor": "PHOENIX",
  "recurrencia_call_terreno": 0,
  "casos_asignados": 0,
  "casos_gestion": 0,
  "porcentaje_gestionado": 0,
  "casos_contacto_titular": 0,
  "porcentaje_contacto_titular": 0,
  "casos_promesa": 0,
  "porcentaje_promesa": 0,
  "promesas_cumplidas": 0,
  "porcentaje_promesa_cumplida": 0
}
```

También se recomienda incorporar estos valores a:

```http
GET /api/contactabilidad/itau-vencida/resumen
```

cuando el frontend necesite mostrarlos en cards o reutilizarlos en otros componentes.

---

# 15. Frontend

En la tabla **Tubo de Contactabilidad por Gestor** agregar después de `% Contacto Titular`:

```text
Casos con Promesa
% Promesa
Promesas Cumplidas
% Promesa Cumplida
```

Orden definitivo:

```text
Gestor
Recurrencia Call + Terreno
Casos Asignados
Casos con Gestión
% Gestionado
Casos con Contacto Titular
% Contacto Titular
Casos con Promesa
% Promesa
Promesas Cumplidas
% Promesa Cumplida
```

Los porcentajes se deben mostrar con el mismo formato del resto del módulo.

Ejemplo:

```text
32,4%
76,8%
```

---

# 16. Detalle

La vista de detalle debe incorporar:

```text
Tiene Promesa
Fecha Última Promesa
Fecha Compromiso
Promesa Cumplida
```

Ejemplo:

| RUT | Tiene Promesa | Última Gestión Promesa | Fecha Compromiso | Contención | Promesa Cumplida |
|---|---|---|---|---:|---|
| 11111111-1 | SI | 04-09-2026 | 10-09-2026 | 150.000 | SI |
| 22222222-2 | SI | 03-09-2026 | 08-09-2026 | 0 | NO |
| 33333333-3 | NO |  |  | 0 | NO |

---

# 17. Evolución diaria

La evolución debe incorporar:

```text
Casos con Promesa
Promesas Cumplidas
% Promesa
% Promesa Cumplida
```

Para cada día, el cálculo debe ser acumulado hasta la fecha correspondiente cuando el gráfico represente avance mensual.

Ejemplo:

```text
Fecha 04-09-2026
Promesas = casos con promesa cuya FechaGestion <= 04-09-2026
```

y:

```text
Promesas Cumplidas =
casos anteriores que además tienen CONTENCION > 0
```

---

# 18. Casos de prueba

## Caso 1 — Un cliente con una promesa y sin pago

Datos:

```text
Promesa = SI
CONTENCION = 0
```

Resultado:

```text
Casos con Promesa += 1
Promesas Cumplidas += 0
```

---

## Caso 2 — Un cliente con promesa y pago

Datos:

```text
Promesa = SI
CONTENCION > 0
```

Resultado:

```text
Casos con Promesa += 1
Promesas Cumplidas += 1
```

---

## Caso 3 — Cliente con tres promesas

Si un cliente tiene tres registros en:

```text
tmp_FECHA_COMPROMISO_CRM
```

durante el período:

```text
Casos con Promesa += 1
```

No:

```text
Casos con Promesa += 3
```

---

## Caso 4 — Promesa fuera del período

Ejemplo:

```text
Período consultado = septiembre 2026
FechaGestion       = 31-08-2026
```

Resultado:

```text
No contar como promesa de septiembre.
```

---

## Caso 5 — Otra cartera

```text
cartera = 520
```

Resultado:

```text
No considerar.
```

Solo:

```text
cartera = 523
```

---

## Caso 6 — Cliente no asignado al universo

Si existe una promesa en CRM pero el caso no pertenece al universo filtrado de Itaú Vencida:

```text
No debe sumarse al Tubo.
```

---

## Caso 7 — División por cero en % Promesa

```text
Casos Contacto Titular = 0
Casos con Promesa      = 0
```

Resultado:

```text
% Promesa = 0%
```

---

## Caso 8 — División por cero en % Promesa Cumplida

```text
Casos con Promesa = 0
```

Resultado:

```text
% Promesa Cumplida = 0%
```

---

## Caso 9 — Promesa con pago

```text
Casos con Promesa = 10
CONTENCION > 0 para 7 de ellos
```

Resultado:

```text
Promesas Cumplidas     = 7
% Promesa Cumplida     = 70%
```

---

# 19. Criterios de aceptación

- [ ] `tmp_FECHA_COMPROMISO_CRM` se utiliza como fuente de Promesas.
- [ ] Todas las consultas a promesas filtran `cartera = 523`.
- [ ] El período se filtra mediante `FechaGestion`.
- [ ] Se utiliza límite superior exclusivo para fechas.
- [ ] Un cliente con múltiples filas de promesa cuenta una sola vez como `Caso con Promesa`.
- [ ] Las promesas se cruzan únicamente contra el universo filtrado del dashboard.
- [ ] `Casos con Promesa` aparece en el Tubo.
- [ ] `% Promesa` se calcula como `Casos con Promesa / Casos con Contacto Titular`.
- [ ] `Promesas Cumplidas` corresponde a casos con promesa y `CONTENCION > 0`.
- [ ] `% Promesa Cumplida` se calcula como `Promesas Cumplidas / Casos con Promesa`.
- [ ] Todas las divisiones manejan denominador cero.
- [ ] Los indicadores responden a todos los filtros activos.
- [ ] No se duplican clientes por múltiples promesas.
- [ ] No se duplican clientes por múltiples filas de contención.
- [ ] El endpoint `/tubo` devuelve los cuatro nuevos campos.
- [ ] La tabla frontend muestra las cuatro columnas nuevas.
- [ ] El detalle permite identificar si un caso tiene promesa y si está cumplida.
- [ ] Los resultados se validan contra consultas SQL de control antes de aprobar el desarrollo.

---

# 20. Validación SQL de control

Una vez identificada la llave real, se deben poder validar por separado los dos principales conteos.

## Casos con Promesa

Ejemplo si la llave fuese RUT:

```sql
SELECT
    COUNT(DISTINCT RUT) AS CASOS_PROMESA
FROM dbo.tmp_FECHA_COMPROMISO_CRM
WHERE cartera = 523
  AND FechaGestion >= '2026-09-01'
  AND FechaGestion < '2026-10-01';
```

Este valor todavía debe cruzarse contra el universo PHOENIX para obtener el indicador definitivo de Nexus.

---

## Casos con Promesa Cumplida

Ejemplo conceptual:

```sql
WITH PROMESAS AS (
    SELECT DISTINCT
        RUT
    FROM dbo.tmp_FECHA_COMPROMISO_CRM
    WHERE cartera = 523
      AND FechaGestion >= '2026-09-01'
      AND FechaGestion < '2026-10-01'
),

CONTENCION AS (
    SELECT
        RUT,
        MAX(
            CASE
                WHEN ISNULL(CONTENCION, 0) > 0 THEN 1
                ELSE 0
            END
        ) AS TIENE_CONTENCION
    FROM dbo.contencion_itau_vencida
    WHERE GESTOR = 'PHOENIX'
    GROUP BY RUT
)

SELECT
    COUNT(*) AS PROMESAS_CUMPLIDAS
FROM PROMESAS P
INNER JOIN CONTENCION C
    ON P.RUT = C.RUT
WHERE C.TIENE_CONTENCION = 1;
```

Nuevamente:

> Esta consulta es únicamente de control. El valor definitivo debe considerar el mismo universo y los mismos filtros aplicados en el dashboard.

---

# 21. Flujo definitivo

```text
Asignación Itaú Vencida
        |
        | Fecha de Proceso
        v
Universo de casos
        |
        | filtros comerciales
        | GESTOR = PHOENIX
        v
Contención Itaú Vencida
        |
        +-----------------------------+
        |                             |
        v                             v
Gestiones CRM                  Promesas CRM
cartera = 523                  cartera = 523
tmp_GEST_CRM                   tmp_FECHA_COMPROMISO_CRM
        |                             |
        |                             |
        +-------------+---------------+
                      |
                      v
              Consolidación por caso
                      |
          +-----------+------------+
          |                        |
          v                        v
    Tiene Promesa          CONTENCION > 0
          |                        |
          +-----------+------------+
                      |
                      v
              Promesa Cumplida
                      |
                      v
         Tubo de Contactabilidad
```

---

# 22. Definición final de negocio

Para esta implementación se debe entender:

```text
CASO CON PROMESA
=
Caso del universo PHOENIX
con al menos una promesa registrada en
tmp_FECHA_COMPROMISO_CRM
para cartera 523
dentro del período consultado.
```

```text
PROMESA CUMPLIDA
=
Caso con Promesa
que además tiene
CONTENCION > 0.
```

Y los porcentajes serán:

```text
% Promesa
=
Casos con Promesa
/
Casos con Contacto Titular
```

```text
% Promesa Cumplida
=
Promesas Cumplidas
/
Casos con Promesa
```
