# Requerimiento funcional y técnico — Módulo Contactabilidad Itaú Vencida

### Información de negocio incorporada

Este requerimiento incluye las siguientes definiciones confirmadas:

- Cartera CRM Itaú Vencida: `523`.
- Gestor de la vista: `PHOENIX`.
- Total Clientes: RUT únicos desde `asignacion_itau_vencida`.
- Filtros comerciales: `contencion_itau_vencida`.
- Estado Contacto: `tmp_GEST_CRM.CONTACTOGESTION`.
- Total Gestiones: acciones `TELEFONICA` + `TERRENO`.
- Estado Contención: `SI` si `CONTENCION > 0`, `NO` si `CONTENCION = 0`.

---

# 1. Objetivo

Crear una nueva vista de **Contactabilidad** en Nexus, disponible en:

`https://nexus.ph.lan/contactabilidad`

La página `/contactabilidad` debe funcionar como una vista contenedora de módulos de contactabilidad por mandante/cartera.

En una primera etapa se debe incorporar una tarjeta para:

**Itaú Vencida**

Al seleccionar la tarjeta, el usuario debe ingresar a una vista específica de **Contactabilidad Itaú Vencida**, visualmente similar al reporte de referencia entregado por Itaú.

El objetivo principal es poder medir, consultar y comparar la gestión de contactabilidad utilizando las siguientes fuentes de SQL Server:

- `contencion_itau_vencida`: atributos, segmentación y filtros de la cartera.
- `asignacion_itau_vencida`: universo de RUT asignados para el cálculo de Total Clientes.
- `tmp_GEST_CRM`: gestiones realizadas, filtradas por `cartera = 523`.

La solución debe calcular los indicadores en backend y entregar al frontend únicamente datos agregados o detalle paginado. No se debe descargar la totalidad de ambas tablas al navegador.

---

# 2. Alcance

## Incluido

1. Crear página principal `/contactabilidad`.
2. Crear tarjeta **Itaú Vencida**.
3. Crear vista de detalle para Itaú Vencida.
4. Conexión a SQL Server.
5. Uso de:
   - `contencion_itau_vencida`
   - `asignacion_itau_vencida`
   - `tmp_GEST_CRM` con `cartera = 523`
6. Filtros de consulta.
7. Tarjetas KPI.
8. Tabla "Estado Contacto Cliente por Gestor".
9. Tabla "Tubo de Contactabilidad por Gestor".
10. Gráfico de gestiones y recurrencia.
11. Evolución diaria.
12. Detalle de clientes/gestiones.
13. Validación de cifras contra reporte Itaú.
14. Manejo de loading, errores y estados sin información.
15. Optimización para grandes volúmenes de datos.

## Fuera de alcance inicial

- Otras carteras de Itaú.
- Otros mandantes.
- Modificación de datos en origen.
- Carga manual de archivos.
- Automatización de la carga de las tablas.
- Réplica exacta pixel a pixel del Power BI original.
- Exportaciones avanzadas, salvo que ya exista un componente reutilizable en Nexus.

---

# 3. Navegación

## 3.1 Página principal

Ruta:

`/contactabilidad`

La vista debe mostrar una sección o grilla de tarjetas.

Primera tarjeta:

### Itaú Vencida

Contenido sugerido:

- Logo/nombre Itaú.
- Título: `Itaú Vencida`.
- Descripción: `Indicadores de contactabilidad, recurrencia, contacto titular y promesas.`
- Estado opcional: `Disponible`.
- Botón o interacción: `Ver detalle`.

Al presionar la tarjeta se debe navegar a:

`/contactabilidad/itau-vencida`

---

# 4. Vista Itaú Vencida

Ruta:

`/contactabilidad/itau-vencida`

La vista debe mantener la estructura visual general del reporte entregado como referencia:

1. Encabezado.
2. Filtros superiores.
3. Tarjetas KPI.
4. Estado de contacto por gestor.
5. Tubo de contactabilidad.
6. Gráfico de gestiones y recurrencia.
7. Evolución diaria.
8. Detalle.

No es necesario copiar estilos antiguos de Power BI. Se debe respetar el diseño visual actual de Nexus, manteniendo una apariencia ejecutiva, compacta y legible.

---

# 5. Fuentes de datos

## 5.1 SQL Server

La conexión debe obtenerse desde variables de entorno/configuración segura.

Datos conocidos:

```env
DB_SERVER=190.110.124.67,11432
DB_NAME=bdphoenixconsultas
DB_USER=phoenix
DB_DRIVER=ODBC Driver 17 for SQL Server
```

La contraseña **no debe quedar hardcodeada** en frontend, repositorio, archivos `.md`, JavaScript, TypeScript ni código Python.

Debe utilizarse una variable de entorno:

```env
DB_PASSWORD=<configurar_en_servidor>
```

---

# 6. Tablas utilizadas

## 6.1 `contencion_itau_vencida`

Rol de la tabla:

**Fuente principal de filtros y atributos de la cartera Itaú Vencida.**

Debe utilizarse para obtener los siguientes filtros:

- Segmento Cliente: `SEGMENTO`
- Canal: `CANAL`
- Gestor: `GESTOR`
- Fase Cliente: `FASE_PROY_MAX`
- Mix Producto: `PRODUCTO`
- Tipo Campaña: `TIPO_CAMPANA`
- Detalle Marca: `DETALLE_MARCA`
- Estado Contención: derivado desde `CONTENCION`

### Regla especial Gestor

El filtro `GESTOR` debe:

- autoseleccionar siempre `PHOENIX`;
- no considerar los demás gestores para esta vista;
- evitar que el usuario consulte gestores ajenos a PHOENIX en el módulo Itaú Vencida.

En términos prácticos, el backend debe trabajar con:

```sql
GESTOR = 'PHOENIX'
```

cuando aplique a la fuente `contencion_itau_vencida`.

### Regla Estado Contención

El campo `CONTENCION` contiene montos, por lo tanto el filtro visible para el usuario debe transformarse a:

```text
SI -> CONTENCION > 0
NO -> CONTENCION = 0
```

Ejemplo SQL:

```sql
CASE
    WHEN ISNULL(CONTENCION, 0) > 0 THEN 'SI'
    ELSE 'NO'
END AS ESTADO_CONTENCION
```

---

## 6.2 `asignacion_itau_vencida`

Rol de la tabla:

**Fuente oficial del universo de clientes/RUT asignados.**

Se utilizará para calcular:

- Total Clientes.
- N° RUT asignados.
- Universo base contra el cual se calcula `% Contacto Gestionado`.

La fecha de la asignación debe corresponder a la **Fecha de Proceso** seleccionada en la vista.

Ejemplo:

```text
Fecha de proceso: 2026-09-01
```

Consulta base:

```sql
SELECT COUNT(DISTINCT RUT) AS UNICOS
FROM dbo.asignacion_itau_vencida
WHERE FECHA_CARGA = '2026-09-01';
```

Regla:

> `FECHA_CARGA` debe ser igual a la Fecha de Proceso utilizada por el dashboard.

---

## 6.3 `tmp_GEST_CRM`

Rol de la tabla:

**Fuente de gestiones realizadas.**

Para esta vista se deben considerar exclusivamente registros correspondientes a:

```sql
cartera = 523
```

Debe utilizarse para identificar:

- Total de gestiones Call + Terreno.
- Clientes gestionados.
- Contacto titular.
- Contacto tercero.
- Gestión Call-Terreno.
- Otras gestiones.
- Estado Contacto.
- Fecha de gestión.
- Acción de gestión.
- Recurrencia.
- Promesas, si la estructura y regla de negocio permiten identificarlas.

Filtro adicional disponible:

- Estado Contacto: `CONTACTOGESTION`


# 7. Levantamiento obligatorio antes de desarrollar

Antes de implementar las reglas definitivas se debe revisar la estructura real de las tres tablas.

Ejecutar:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN (
    'contencion_itau_vencida',
    'asignacion_itau_vencida',
    'tmp_GEST_CRM'
)
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

También revisar muestras:

```sql
SELECT TOP 20 *
FROM dbo.contencion_itau_vencida;

SELECT TOP 20 *
FROM dbo.asignacion_itau_vencida;

SELECT TOP 20 *
FROM dbo.tmp_GEST_CRM
WHERE cartera = 523;
```

El desarrollador debe documentar qué columna representa cada concepto de negocio y validar los valores reales presentes en `CONTACTOGESTION` y `AccionGestion`.


# 8. Mapeo de negocio requerido

El siguiente mapeo ya se encuentra parcialmente definido y debe respetarse:

| Concepto | Tabla | Columna / regla |
|---|---|---|
| Segmento Cliente | `contencion_itau_vencida` | `SEGMENTO` |
| Canal | `contencion_itau_vencida` | `CANAL` |
| Gestor | `contencion_itau_vencida` | `GESTOR = 'PHOENIX'` |
| Fase Cliente | `contencion_itau_vencida` | `FASE_PROY_MAX` |
| Mix Producto | `contencion_itau_vencida` | `PRODUCTO` |
| Tipo Campaña | `contencion_itau_vencida` | `TIPO_CAMPANA` |
| Detalle Marca | `contencion_itau_vencida` | `DETALLE_MARCA` |
| Estado Contención | `contencion_itau_vencida` | `CONTENCION > 0 => SI`, `CONTENCION = 0 => NO` |
| Total Clientes | `asignacion_itau_vencida` | `COUNT(DISTINCT RUT)` |
| Fecha de proceso | `asignacion_itau_vencida` | `FECHA_CARGA` |
| Cartera CRM | `tmp_GEST_CRM` | `cartera = 523` |
| Fecha gestión | `tmp_GEST_CRM` | `GestionFecha` |
| Acción gestión | `tmp_GEST_CRM` | `AccionGestion` |
| Estado Contacto | `tmp_GEST_CRM` | `CONTACTOGESTION` |
| Contacto Titular | `tmp_GEST_CRM` | `CONTACTOGESTION = 'TITULAR'` |
| Contacto Tercero | `tmp_GEST_CRM` | valor equivalente a tercero en `CONTACTOGESTION`, validar valor exacto |
| Gestión Call-Terreno | `tmp_GEST_CRM` | `AccionGestion IN ('TELEFONICA','TERRENO')` |
| Otras Gestiones | `tmp_GEST_CRM` | `AccionGestion NOT IN ('TELEFONICA','TERRENO')` |

Pendiente de validar:

- columna exacta usada para identificar un cliente único en `tmp_GEST_CRM`;
- valor exacto de `CONTACTOGESTION` para contacto tercero;
- definición exacta de "Gestionado" a nivel de cliente/RUT;
- campos y regla de promesa/promesa cumplida, si se incluirán en esta etapa.


# 9. Regla de cruce entre las fuentes

La solución no debe hacer un `JOIN` directo de las tablas completas sin validar cardinalidad.

La lógica debe ser:

```text
asignacion_itau_vencida
        |
        | universo de RUT según FECHA_CARGA
        v
contencion_itau_vencida
        |
        | atributos y filtros de cartera
        v
tmp_GEST_CRM
        |
        | gestiones de cartera 523
        v
indicadores
```

Antes de definir el cruce se debe identificar la llave común real, preferentemente RUT normalizado y, cuando exista, operación/período.

Se debe comprobar si un RUT aparece más de una vez en cada fuente.

Ejemplo:

```sql
SELECT
    RUT,
    COUNT(*) AS cantidad
FROM dbo.asignacion_itau_vencida
WHERE FECHA_CARGA = '2026-09-01'
GROUP BY RUT
HAVING COUNT(*) > 1
ORDER BY cantidad DESC;
```

El cálculo de `Total Clientes` debe seguir utilizando `COUNT(DISTINCT RUT)`, independientemente de que existan múltiples filas para un mismo RUT.

Para las gestiones, primero se debe agregar/clasificar por cliente cuando el indicador sea de clientes únicos, evitando que múltiples gestiones dupliquen el universo.


# 10. Regla temporal

La vista debe trabajar con una **Fecha de Proceso**.

Ejemplo:

```text
Fecha de proceso: 2026-09-01
```

Esta fecha controla el universo de asignación:

```sql
FECHA_CARGA = '2026-09-01'
```

Para las gestiones CRM se debe trabajar con el período mensual correspondiente a la Fecha de Proceso.

Ejemplo para septiembre 2026:

```sql
GestionFecha >= '2026-09-01'
AND GestionFecha < '2026-10-01'
```

Se recomienda utilizar límite superior exclusivo en lugar de:

```sql
BETWEEN '2026-09-01' AND '2026-09-30'
```

porque `GestionFecha` puede ser `datetime` y contener hora.

Por lo tanto:

```text
Fecha de proceso = 2026-09-01
Universo         = FECHA_CARGA 2026-09-01
Gestiones        = 2026-09-01 00:00:00 hasta antes de 2026-10-01 00:00:00
```

Si posteriormente negocio define que "Resultado al día" debe cortar gestiones en una fecha distinta al fin de mes, se deberá parametrizar `fecha_hasta`. Para el requerimiento actual, la regla suministrada corresponde al mes completo de la Fecha de Proceso.


# 11. Filtros

La barra superior debe contener los siguientes filtros.

## Desde `contencion_itau_vencida`

| Filtro visible | Columna | Regla |
|---|---|---|
| Segmento Cliente | `SEGMENTO` | Multiselección |
| Canal | `CANAL` | Multiselección |
| Gestor | `GESTOR` | Debe quedar autoseleccionado en `PHOENIX`; no considerar otros gestores |
| Fase Cliente | `FASE_PROY_MAX` | Multiselección |
| Mix Producto | `PRODUCTO` | Multiselección |
| Tipo Campaña | `TIPO_CAMPANA` | Multiselección |
| Detalle Marca | `DETALLE_MARCA` | Multiselección |
| Estado Contención | `CONTENCION` | Mostrar `SI` si monto > 0 y `NO` si monto = 0 |

## Desde `tmp_GEST_CRM`

Siempre aplicar:

```sql
cartera = 523
```

Filtro:

| Filtro visible | Columna |
|---|---|
| Estado Contacto | `CONTACTOGESTION` |

## Fecha

Agregar:

- Fecha de Proceso.

La Fecha de Proceso debe seleccionar el universo desde:

```sql
asignacion_itau_vencida.FECHA_CARGA
```


# 12. Comportamiento de filtros

Cada modificación de filtro debe refrescar:

- KPI.
- Estado de contacto.
- Tubo de contactabilidad.
- Gráficos.
- Evolución.
- Detalle.

No se debe recargar la página completa.

Se debe utilizar el patrón ya definido por Nexus para consultas API, estados de carga y manejo de errores.

Los filtros multiselección deben enviar valores al backend de forma segura y parametrizada.

---

# 13. Indicadores KPI

La fila principal debe contener las tarjetas del reporte de referencia.

## 13.1 Total Gestiones / Call + Terreno

Fuente:

`tmp_GEST_CRM`

Reglas:

```sql
cartera = 523
AccionGestion IN ('TELEFONICA', 'TERRENO')
GestionFecha dentro del mes de la Fecha de Proceso
```

Consulta base para septiembre 2026:

```sql
SELECT COUNT(*) AS TOTAL_GESTIONES
FROM dbo.tmp_GEST_CRM
WHERE cartera = 523
  AND GestionFecha >= '2026-09-01'
  AND GestionFecha < '2026-10-01'
  AND AccionGestion IN ('TELEFONICA', 'TERRENO');
```

La tarjeta debe mostrar:

```text
TOTAL GESTIONES
Call + Terreno
```

---

## 13.2 Total Clientes / N° RUT Asignados

Fuente:

`asignacion_itau_vencida`

Definición:

```sql
SELECT COUNT(DISTINCT RUT) AS TOTAL_CLIENTES
FROM dbo.asignacion_itau_vencida
WHERE FECHA_CARGA = '2026-09-01';
```

Regla:

> `FECHA_CARGA` debe ser igual a la Fecha de Proceso.

La tarjeta debe mostrar:

```text
TOTAL CLIENTES
N RUT asignados
```

---

## 13.3 Recurrencia Promedio

Definición:

```text
Total Gestiones Call + Terreno / Total Clientes
```

Usar manejo seguro de división por cero.

Ejemplo:

```text
311.046 / 5.104 = 60,9
```

---

## 13.4 % Contacto Gestionado

Definición:

```text
Clientes Gestionados / Total Clientes
```

`Clientes Gestionados` debe contar RUT únicos del universo que tengan al menos una gestión válida de acuerdo con la regla definitiva de negocio.

No se debe usar `COUNT(*)` para el numerador si un mismo RUT posee múltiples gestiones.

---

## 13.5 % Contacto Titular

Definición:

```text
Clientes con Contacto Titular / Total Gestionado
```

Fuente:

`tmp_GEST_CRM`

Regla de contacto titular:

```sql
cartera = 523
CONTACTOGESTION = 'TITULAR'
GestionFecha dentro del mes de la Fecha de Proceso
```

Consulta de control de registros:

```sql
SELECT COUNT(*) AS REGISTROS_CONTACTO_TITULAR
FROM dbo.tmp_GEST_CRM
WHERE cartera = 523
  AND GestionFecha >= '2026-09-01'
  AND GestionFecha < '2026-10-01'
  AND CONTACTOGESTION = 'TITULAR';
```

Para el KPI porcentual, si un mismo RUT puede tener múltiples registros TITULAR, el numerador debe consolidarse por cliente/RUT para evitar duplicaciones.


# 14. Indicadores complementarios

El backend debe calcular además:

- Clientes gestionados únicos.
- Clientes con contacto titular.
- Clientes con contacto tercero.
- Clientes con gestión Call-Terreno.
- Clientes con otras gestiones.
- Clientes sin gestión.
- Recurrencia Call + Terreno.

Si se incorporan Promesas y Promesas Cumplidas, primero se debe definir y documentar la regla exacta en los campos disponibles de `tmp_GEST_CRM`.


# 15. Clasificación del estado de contacto

Para la tabla de estado de contacto, se deben calcular las siguientes categorías:

1. Contacto Titular.
2. Contacto Tercero.
3. Gestión Call-Terreno.
4. Otras Gestiones.

Reglas conocidas:

### Contacto Titular

```sql
CONTACTOGESTION = 'TITULAR'
```

### Contacto Tercero

Utilizar `CONTACTOGESTION`, validando previamente el valor exacto existente en base para "TERCERO".

### Gestión Call-Terreno

```sql
AccionGestion IN ('TELEFONICA', 'TERRENO')
```

### Otras Gestiones

```sql
AccionGestion NOT IN ('TELEFONICA', 'TERRENO')
```

Siempre restringiendo CRM a:

```sql
cartera = 523
```

Si un mismo RUT puede pertenecer a más de una categoría durante el período, se debe definir una prioridad de consolidación para que la tabla de clientes no duplique personas.

Prioridad sugerida, sujeta a validación:

```text
Contacto Titular
    >
Contacto Tercero
    >
Gestión Call-Terreno
    >
Otras Gestiones
```


# 16. Tabla — Estado Contacto Cliente por Gestor

Debe existir una tabla equivalente a:

**Estado Contacto Cliente por Gestor**

Para esta vista el gestor debe ser `PHOENIX`.

Columnas mínimas:

| Gestor | Total general | % | Contacto Titular | % | Contacto Tercero | % | Gestión Call-Terreno | % | Otras Gestiones | % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Reglas

### Total General

Debe ser igual a:

```text
Total Clientes
```

Es decir:

```sql
COUNT(DISTINCT RUT)
FROM asignacion_itau_vencida
WHERE FECHA_CARGA = FechaProceso
```

### Contacto Titular

Cantidad de clientes/RUT únicos con:

```sql
CONTACTOGESTION = 'TITULAR'
```

El porcentaje es:

```text
Contacto Titular / Total General
```

### Contacto Tercero

Misma lógica que Contacto Titular, cambiando el valor de `CONTACTOGESTION` al correspondiente a tercero.

El porcentaje es:

```text
Contacto Tercero / Total General
```

### Gestión Call-Terreno

Gestiones/clientes correspondientes a:

```sql
AccionGestion IN ('TELEFONICA', 'TERRENO')
```

La implementación debe definir si la tabla muestra clientes únicos o gestiones; dado que la tabla es "Estado Contacto Cliente", se recomienda consolidar por RUT único.

### Otras Gestiones

Corresponde a gestiones cuya acción no sea telefónica ni terreno:

```sql
AccionGestion NOT IN ('TELEFONICA', 'TERRENO')
```

También se recomienda consolidar por RUT único.

La tabla debe permitir validar que los clientes no queden duplicados entre estados cuando se aplique una clasificación única.


# 17. Tabla — Tubo de Contactabilidad por Gestor

Debe existir una segunda tabla:

**Tubo de Contactabilidad por Gestor**

Columnas mínimas:

| Gestor | Recurrencia Call + Terreno | Casos Asignados | Casos con Gestión | % Gestionado | Casos con Contacto Titular | % Contacto Titular | Casos con Promesa | % Promesa | Promesas Cumplidas | % Promesa Cumplida |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

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

Todas las divisiones deben ser seguras ante cero.

---

# 18. Gráfico — Gestiones y Recurrencia Promedio

Crear gráfico combinado.

Título sugerido:

**Total Gestiones Call-Terreno y Recurrencia Promedio por Cliente**

Visual:

- Barras: total de gestiones.
- Línea: recurrencia promedio.

Dimensión:

- Gestor.

Debe responder a todos los filtros superiores.

---

# 19. Evolución diaria

Crear una sección de evolución por día.

Métricas mínimas:

- Total gestiones.
- Clientes gestionados.
- % gestionado.
- Contacto titular.
- % contacto titular.
- Promesas.
- Promesas cumplidas.

Eje X:

`Fecha`

Debe ser posible ver cómo evoluciona el mes hasta la fecha seleccionada.

---

# 20. Vista detalle

Debe existir una tabla de detalle accesible desde la misma página o mediante pestaña interna.

Campos sugeridos:

- RUT.
- Operación.
- Gestor asignado.
- Segmento.
- Producto.
- Estado contención.
- Cantidad de gestiones.
- Fecha última gestión.
- Último resultado.
- Estado de contacto consolidado.
- Tiene promesa.
- Promesa cumplida.

La tabla debe ser paginada desde backend.

No cargar todo el detalle al navegador.

Agregar búsqueda por:

- RUT.
- Operación.

---

# 21. API propuesta

Prefijo sugerido:

`/api/contactabilidad/itau-vencida`

## 21.1 Filtros

```http
GET /api/contactabilidad/itau-vencida/filtros
```

Parámetros opcionales:

```text
periodo
fecha_hasta
```

Respuesta esperada:

```json
{
  "fechas_proceso": [],
  "segmentos": [],
  "canales": [],
  "gestores": ["PHOENIX"],
  "fases_cliente": [],
  "productos": [],
  "tipos_campana": [],
  "detalles_marca": [],
  "estados_contencion": ["SI", "NO"],
  "estados_contacto": []
}
```

---

## 21.2 Resumen

```http
GET /api/contactabilidad/itau-vencida/resumen
```

Parámetros:

```text
periodo
fecha_hasta
gestor
canal
segmento
producto
estado_contacto
```

Respuesta ejemplo:

```json
{
  "total_gestiones": 182202,
  "total_clientes": 2222,
  "clientes_gestionados": 2222,
  "recurrencia": 82.0,
  "porcentaje_gestionado": 100.0,
  "contacto_titular": 1065,
  "porcentaje_contacto_titular": 47.9,
  "clientes_promesa": 345,
  "promesas_cumplidas": 265,
  "porcentaje_promesa": 32.4,
  "porcentaje_promesa_cumplida": 76.8
}
```

---

## 21.3 Estado contacto

```http
GET /api/contactabilidad/itau-vencida/estado-contacto
```

Debe devolver información agrupada por gestor.

---

## 21.4 Tubo

```http
GET /api/contactabilidad/itau-vencida/tubo
```

Debe devolver indicadores agrupados por gestor.

---

## 21.5 Evolución

```http
GET /api/contactabilidad/itau-vencida/evolucion
```

Debe entregar serie diaria.

---

## 21.6 Detalle

```http
GET /api/contactabilidad/itau-vencida/detalle
```

Parámetros adicionales:

```text
page
page_size
search
sort_by
sort_direction
```

La paginación debe ejecutarse en SQL/backend.

---

# 22. Estructura de consulta recomendada

No ejecutar consultas independientes complejas para cada KPI si pueden obtenerse desde una misma agregación.

Flujo conceptual:

```text
1. Construir universo filtrado.
2. Normalizar llave cliente/operación.
3. Obtener gestiones válidas hasta fecha seleccionada.
4. Agregar gestiones por cliente.
5. Clasificar mejor estado de contacto.
6. Cruzar agregado de gestiones con universo.
7. Calcular métricas.
8. Agrupar según endpoint.
```

Nunca:

```text
contencion_itau_vencida
JOIN
tmp_GEST_CRM
```

sin comprobar previamente la cardinalidad.

Esto podría multiplicar artificialmente filas y alterar:

- gestiones,
- recurrencia,
- contactos,
- promesas.

---

# 23. SQL — validaciones iniciales

## Conteo de registros

```sql
SELECT COUNT(*) AS registros
FROM dbo.contencion_itau_vencida;

SELECT COUNT(*) AS registros
FROM dbo.tmp_GEST_CRM;
```

## Duplicidad por RUT

Adaptar nombre real de columna:

```sql
SELECT
    rut,
    COUNT(*) AS cantidad
FROM dbo.contencion_itau_vencida
GROUP BY rut
HAVING COUNT(*) > 1
ORDER BY cantidad DESC;
```

## Rango de fechas CRM

```sql
SELECT
    MIN(fecha_gestion) AS fecha_min,
    MAX(fecha_gestion) AS fecha_max
FROM dbo.tmp_GEST_CRM;
```

## Volumen diario

```sql
SELECT
    CAST(fecha_gestion AS date) AS fecha,
    COUNT(*) AS gestiones
FROM dbo.tmp_GEST_CRM
GROUP BY CAST(fecha_gestion AS date)
ORDER BY fecha DESC;
```

Los nombres de campos deben ajustarse a la estructura real.

---

# 23.1 Consultas de referencia obligatorias

Estas consultas representan las reglas de negocio suministradas y deben utilizarse como controles durante el desarrollo.

## Total Gestiones Call + Terreno

```sql
SELECT COUNT(*) AS TOTAL_GESTIONES
FROM dbo.tmp_GEST_CRM
WHERE cartera = 523
  AND GestionFecha >= '2026-09-01'
  AND GestionFecha < '2026-10-01'
  AND AccionGestion IN ('TELEFONICA', 'TERRENO');
```

## Total Clientes

```sql
SELECT COUNT(DISTINCT RUT) AS TOTAL_CLIENTES
FROM dbo.asignacion_itau_vencida
WHERE FECHA_CARGA = '2026-09-01';
```

## Registros Contacto Titular

```sql
SELECT COUNT(*) AS REGISTROS_CONTACTO_TITULAR
FROM dbo.tmp_GEST_CRM
WHERE cartera = 523
  AND GestionFecha >= '2026-09-01'
  AND GestionFecha < '2026-10-01'
  AND CONTACTOGESTION = 'TITULAR';
```

## Validar valores de Estado Contacto

```sql
SELECT
    CONTACTOGESTION,
    COUNT(*) AS cantidad
FROM dbo.tmp_GEST_CRM
WHERE cartera = 523
GROUP BY CONTACTOGESTION
ORDER BY cantidad DESC;
```

## Validar valores de Acción Gestión

```sql
SELECT
    AccionGestion,
    COUNT(*) AS cantidad
FROM dbo.tmp_GEST_CRM
WHERE cartera = 523
GROUP BY AccionGestion
ORDER BY cantidad DESC;
```

## Validar Gestor en contención

```sql
SELECT
    GESTOR,
    COUNT(*) AS cantidad
FROM dbo.contencion_itau_vencida
GROUP BY GESTOR
ORDER BY cantidad DESC;
```

La vista debe utilizar exclusivamente `PHOENIX` para el filtro Gestor.

---

# 24. Performance

La página debe responder correctamente aun cuando las tablas tengan gran volumen.

Requisitos:

1. Filtrar en SQL, no en frontend.
2. Seleccionar únicamente columnas necesarias.
3. Evitar `SELECT *` en endpoints productivos.
4. Parametrizar consultas.
5. Revisar índices sobre:
   - fecha/período,
   - RUT,
   - operación,
   - gestor,
   - campos usados para joins.
6. Agregar antes de unir cuando corresponda.
7. Paginar detalle.
8. Evitar N+1 queries.
9. No realizar una consulta por fila.
10. Cachear catálogos/filtros si corresponde.
11. Cancelar/refrescar requests cuando el usuario cambie filtros rápidamente.

Objetivo inicial sugerido:

- KPI y tablas agregadas: idealmente < 3 segundos.
- Detalle paginado: idealmente < 5 segundos.

Si el volumen impide estos tiempos, revisar índices, vistas/materialización o tablas agregadas.

---

# 25. Seguridad

1. No exponer credenciales SQL al navegador.
2. Frontend nunca debe conectarse directamente a SQL Server.
3. Toda conexión SQL debe ejecutarse desde backend.
4. Utilizar queries parametrizadas.
5. Validar listas de filtros.
6. Limitar `page_size`.
7. Sanitizar búsqueda.
8. Respetar autenticación/autorización actual de Nexus.
9. No registrar contraseñas en logs.
10. No enviar información sensible innecesaria al frontend.

---

# 26. Diseño visual

La referencia del reporte Itaú debe utilizarse como inspiración funcional.

El diseño debe adaptarse al sistema visual de Nexus.

## Encabezado

Título:

**Contactabilidad Itaú Vencida**

Subtítulo:

`Resultado al día DD-MM-YYYY`

## Colores

Utilizar principalmente el sistema de colores de Nexus.

Se puede utilizar un acento naranja asociado a Itaú para:

- título,
- borde,
- badge,
- iconografía secundaria.

No es necesario replicar completamente el naranja/azul del Power BI.

## Layout desktop sugerido

```text
┌─────────────────────────────────────────────────────────────┐
│ Contactabilidad Itaú Vencida            Resultado al día    │
├─────────────────────────────────────────────────────────────┤
│ Período │ Fecha │ Gestor │ Canal │ Segmento │ Producto ... │
├─────────────────────────────────────────────────────────────┤
│ Total      Total       Recurrencia    % Gestión   % Titular │
│ Gestiones  Clientes    Promedio                              │
├─────────────────────────────────────────────────────────────┤
│ Estado Contacto Cliente por Gestor                          │
│                                                             │
│ [tabla]                                                     │
├─────────────────────────────────────────────────────────────┤
│ Tubo de Contactabilidad por Gestor                          │
│                                                             │
│ [tabla]                                                     │
├─────────────────────────────────────────────────────────────┤
│ Total Gestiones + Recurrencia por Gestor                    │
│                                                             │
│ [gráfico combinado]                                         │
├─────────────────────────────────────────────────────────────┤
│ Evolución diaria                                            │
│                                                             │
│ [gráfico]                                                   │
├─────────────────────────────────────────────────────────────┤
│ Detalle                                                     │
│ [búsqueda] [tabla paginada]                                 │
└─────────────────────────────────────────────────────────────┘
```

---

# 27. Responsive

La prioridad es escritorio, dado que corresponde a una herramienta de gestión.

Sin embargo:

- No debe romperse en resoluciones menores.
- Las tarjetas KPI deben reorganizarse.
- Los filtros deben wrappear.
- Las tablas pueden tener scroll horizontal cuando sea inevitable.
- No generar scroll horizontal global de toda la página.

---

# 28. Estados de interfaz

## Loading

Mostrar skeletons o loaders independientes para:

- KPI.
- Tablas.
- Gráficos.
- Detalle.

## Sin datos

Mensaje:

`No existen datos para los filtros seleccionados.`

No mostrar `NaN`, `Infinity` ni porcentajes inválidos.

## Error

Mensaje general:

`No fue posible cargar la información de contactabilidad.`

Agregar acción:

`Reintentar`

El error técnico debe registrarse en backend/logs, no mostrarse completo al usuario.

---

# 29. Formato de valores

## Números

Ejemplo:

```text
182.202
```

## Porcentajes

Ejemplo:

```text
47,9%
```

## Recurrencia

Ejemplo:

```text
82,0
```

## Fechas

UI:

```text
01-09-2026
```

API/SQL:

```text
2026-09-01
```

---

# 30. Validación contra reporte Itaú

Antes de aprobar el desarrollo se debe seleccionar una fecha cerrada que exista tanto en el reporte Itaú como en la base.

Ejemplo:

`01-09-2026`

Aplicar los mismos filtros.

Comparar:

| Indicador | Itaú | Nexus | Diferencia |
|---|---:|---:|---:|
| Total Gestiones | | | |
| Total Clientes | | | |
| Clientes Gestionados | | | |
| % Gestionado | | | |
| Contacto Titular | | | |
| % Contacto Titular | | | |
| Contacto Tercero | | | |
| Promesas | | | |
| % Promesa | | | |
| Promesas Cumplidas | | | |
| % Promesa Cumplida | | | |
| Recurrencia | | | |

Objetivo:

Los valores deben coincidir.

Si no coinciden, la diferencia debe quedar explicada mediante una regla de negocio documentada.

---

# 31. Criterios de aceptación funcionales

## Página principal

- [ ] Existe `/contactabilidad`.
- [ ] La página carga sin errores.
- [ ] Existe tarjeta `Itaú Vencida`.
- [ ] La tarjeta respeta diseño Nexus.
- [ ] Al presionarla navega a `/contactabilidad/itau-vencida`.

## Itaú Vencida

- [ ] La vista carga correctamente.
- [ ] Se visualiza período.
- [ ] Se visualiza fecha de proceso.
- [ ] Existen filtros.
- [ ] Los filtros actualizan la información sin recargar toda la página.
- [ ] Existe KPI Total Gestiones.
- [ ] Existe KPI Total Clientes.
- [ ] Existe KPI Recurrencia.
- [ ] Existe KPI % Gestionado.
- [ ] Existe KPI % Contacto Titular.
- [ ] Existe tabla Estado Contacto por Gestor.
- [ ] Existe tabla Tubo de Contactabilidad.
- [ ] Existe gráfico Gestiones + Recurrencia.
- [ ] Existe evolución diaria.
- [ ] Existe detalle paginado.
- [ ] Existe fila TOTAL donde corresponda.
- [ ] Porcentajes manejan división por cero.
- [ ] Los valores están correctamente formateados.
- [ ] La información responde al período y fecha seleccionados.
- [ ] El filtro Gestor se carga automáticamente en `PHOENIX`.
- [ ] No se consideran otros gestores en esta vista.
- [ ] Estado Contención muestra `SI` cuando `CONTENCION > 0` y `NO` cuando `CONTENCION = 0`.
- [ ] Todas las consultas CRM aplican `cartera = 523`.
- [ ] Total Gestiones considera únicamente `TELEFONICA` y `TERRENO`.
- [ ] Total Clientes se calcula con `COUNT(DISTINCT RUT)` desde `asignacion_itau_vencida`.
- [ ] `FECHA_CARGA` de asignación coincide con la Fecha de Proceso.

---

# 32. Criterios de aceptación técnicos

- [ ] Se utilizan `contencion_itau_vencida`, `asignacion_itau_vencida` y `tmp_GEST_CRM` según las responsabilidades definidas.
- [ ] No existen credenciales en frontend.
- [ ] No existe contraseña SQL hardcodeada.
- [ ] Queries parametrizadas.
- [ ] No se carga el universo completo al navegador.
- [ ] El detalle está paginado desde backend.
- [ ] No existe `SELECT *` en endpoints productivos.
- [ ] El cruce entre tablas no duplica gestiones.
- [ ] Se validó cardinalidad.
- [ ] Se registran errores de backend.
- [ ] El frontend maneja loading/error/sin datos.
- [ ] La API respeta autenticación actual de Nexus.
- [ ] Los cambios no afectan módulos existentes.

---

# 33. Casos de prueba mínimos

## Caso 1 — Cliente sin gestión

Dado un cliente presente en `contencion_itau_vencida` sin registros en `tmp_GEST_CRM`:

Debe:

- sumar en Total Clientes,
- no sumar en Clientes Gestionados,
- quedar clasificado como Sin Gestión.

---

## Caso 2 — Cliente con múltiples gestiones

Dado un cliente con 15 gestiones:

Debe:

- sumar 15 en Total Gestiones,
- sumar 1 en Clientes Gestionados.

---

## Caso 3 — Contacto titular

Dado un cliente con una gestión sin contacto y posteriormente un contacto titular:

Debe clasificarse como:

`Contacto Titular`

una sola vez.

---

## Caso 4 — Cambio de gestor

Si un filtro selecciona PHOENIX:

Solo deben mostrarse los clientes pertenecientes a PHOENIX según la definición de negocio acordada.

---

## Caso 5 — División por cero

Si no existen clientes gestionados:

```text
% Contacto Titular = 0%
```

No:

```text
NaN
Infinity
Error
```

---

## Caso 6 — Fecha hasta

Si se selecciona:

`15-09-2026`

No deben incluirse gestiones posteriores al 15-09-2026.

---

## Caso 7 — Filtros combinados

Ejemplo:

```text
Periodo: 2026-09
Gestor: PHOENIX
Canal: TERRENO
Producto: X
```

Todos los componentes deben mostrar exactamente el mismo universo filtrado.

---

# 34. Orden de implementación

## Etapa 1 — Levantamiento

1. Revisar columnas.
2. Identificar llave.
3. Identificar período.
4. Identificar gestor.
5. Identificar códigos de resultado.
6. Identificar contacto titular.
7. Identificar contacto tercero.
8. Identificar promesa.
9. Identificar promesa cumplida.
10. Documentar reglas.

### Entregable

Mapa de datos completo.

---

## Etapa 2 — SQL

1. Construir universo.
2. Construir gestiones filtradas.
3. Agregar gestión por cliente.
4. Consolidar estado.
5. Validar totales.
6. Validar joins.
7. Comparar contra reporte Itaú.

### Entregable

Queries validadas.

---

## Etapa 3 — Backend

1. Crear módulo/router.
2. Crear acceso a datos.
3. Crear endpoint filtros.
4. Crear endpoint resumen.
5. Crear endpoint estado contacto.
6. Crear endpoint tubo.
7. Crear endpoint evolución.
8. Crear endpoint detalle.
9. Agregar manejo de errores.
10. Agregar logs.

### Entregable

API funcional.

---

## Etapa 4 — Frontend `/contactabilidad`

1. Crear ruta.
2. Crear layout.
3. Crear tarjeta Itaú Vencida.
4. Agregar navegación.

### Entregable

Hub de Contactabilidad.

---

## Etapa 5 — Frontend Itaú

1. Header.
2. Barra de filtros.
3. Cards.
4. Tabla Estado Contacto.
5. Tabla Tubo.
6. Gráfico Gestiones/Recurrencia.
7. Evolución.
8. Detalle.
9. Loading/error.
10. Responsive.

### Entregable

Vista completa.

---

## Etapa 6 — QA

1. Comparación contra reporte Itaú.
2. Pruebas de filtros.
3. Pruebas de fechas.
4. Pruebas de división por cero.
5. Pruebas de duplicidad.
6. Performance.
7. Responsive.
8. Regresión Nexus.

---

# 35. Prioridad de entrega

## MVP — obligatorio

1. `/contactabilidad`.
2. Tarjeta Itaú Vencida.
3. `/contactabilidad/itau-vencida`.
4. Período.
5. Fecha hasta.
6. Gestor.
7. Cards KPI.
8. Estado Contacto.
9. Tubo de Contactabilidad.
10. Validación contra reporte.

## Segunda iteración

1. Filtros adicionales.
2. Gráficos.
3. Evolución diaria.
4. Detalle.
5. Exportación si se requiere.

---

# 36. Definición de terminado

El requerimiento se considera terminado cuando:

1. El usuario puede entrar a:

   `https://nexus.ph.lan/contactabilidad`

2. Visualiza una tarjeta:

   `Itaú Vencida`

3. Ingresa a:

   `https://nexus.ph.lan/contactabilidad/itau-vencida`

4. Selecciona período, fecha y filtros.

5. La página obtiene información desde SQL Server usando únicamente las fuentes definidas.

6. Puede visualizar los principales KPI de contactabilidad.

7. Puede revisar los indicadores por gestor.

8. Puede revisar el tubo de contactabilidad.

9. Los valores han sido contrastados contra el reporte Itaú.

10. No existen duplicaciones derivadas del cruce de tablas.

11. La aplicación mantiene la seguridad y estructura visual de Nexus.

---

# 37. Observaciones importantes

- No asumir que RUT es automáticamente la llave correcta.
- No asumir que cada fila de `contencion_itau_vencida` representa una persona única.
- No asumir que todas las filas de `tmp_GEST_CRM` son gestiones válidas.
- No inventar equivalencias de códigos CRM.
- Validar las reglas de negocio antes de cerrar las consultas.
- Priorizar exactitud del dato antes que replicar todos los gráficos.
- La primera validación debe ser numérica.
- La réplica visual puede ajustarse una vez que las cifras sean correctas.

---

# 38. Resultado esperado

La solución final debe permitir pasar de:

```text
Reporte externo / Power BI Itaú
```

a:

```text
Nexus
└── Contactabilidad
    └── Itaú Vencida
        ├── Filtros
        ├── KPI
        ├── Estado Contacto
        ├── Tubo Contactabilidad
        ├── Evolución
        └── Detalle
```

Con datos obtenidos directamente desde las tablas de Phoenix y una lógica de negocio validada y documentada.
