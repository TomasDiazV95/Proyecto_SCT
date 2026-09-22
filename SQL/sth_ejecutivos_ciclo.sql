/* ============================================================================
   dbo.sth_ejecutivos_ciclo
   Asignacion mensual de que ciclos ve cada ejecutivo, por producto.

   Reemplaza a dbo.sth_hipotecario_ejecutivos_ciclo, que solo cubria el producto
   hipotecario. La tabla antigua se deja intacta como respaldo.

   Reglas que aplica el backend (WEB/backend/services/sth_service.py):
     - Si un producto NO tiene filas activas para el periodo, su bloque se
       calcula sin filtrar por ciclo (comportamiento historico).
     - El ejecutivo 'Grupal' queda siempre exento del filtro y conserva todos
       sus ciclos, sin importar lo que se configure aca.
     - Los ponderadores de dbo.sth_metas_mensuales deben cuadrar con esta
       asignacion: si cada ejecutivo ve un solo ciclo, cada ciclo va al 100%.

   Script idempotente: se puede reejecutar sin duplicar filas.
   ============================================================================ */

IF OBJECT_ID('dbo.sth_ejecutivos_ciclo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.sth_ejecutivos_ciclo (
        periodo   DATE          NOT NULL,
        producto  VARCHAR(20)   NOT NULL,  -- hipotecario | consumo | pyme | tarjeta
        ejecutivo NVARCHAR(200) NOT NULL,  -- nombre tal cual viene en tmp_carterizado_STH
        ciclo     INT           NOT NULL,
        activo    BIT           NOT NULL
            CONSTRAINT DF_sth_ejecutivos_ciclo_activo DEFAULT (1),
        CONSTRAINT PK_sth_ejecutivos_ciclo
            PRIMARY KEY (periodo, producto, ejecutivo, ciclo)
    );
END
GO


/* ----------------------------------------------------------------------------
   1) Migracion de la configuracion historica de hipotecario
   ---------------------------------------------------------------------------- */

INSERT INTO dbo.sth_ejecutivos_ciclo (periodo, producto, ejecutivo, ciclo, activo)
SELECT
    h.periodo,
    'hipotecario',
    LTRIM(RTRIM(h.ejecutivo)),
    h.ciclo,
    h.activo
FROM dbo.sth_hipotecario_ejecutivos_ciclo h
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.sth_ejecutivos_ciclo e
    WHERE e.periodo = h.periodo
      AND e.producto = 'hipotecario'
      AND e.ejecutivo = LTRIM(RTRIM(h.ejecutivo))
      AND e.ciclo = h.ciclo
);
GO


/* ----------------------------------------------------------------------------
   2) Carga mensual

   Los ciclos de consumo y pyme de 2026-09 estan confirmados por negocio.
   Hipotecario no se carga aca: viene migrado desde la tabla antigua en el
   paso 1, y desde octubre en adelante se agrega a este mismo bloque.

   Para el mes siguiente: copiar el bloque, cambiar la fecha y los ejecutivos.
   ---------------------------------------------------------------------------- */

MERGE dbo.sth_ejecutivos_ciclo AS target
USING (
              SELECT CAST('2026-09-01' AS DATE) AS periodo, 'consumo' AS producto, N'Ana Monardes'      AS ejecutivo, 1 AS ciclo
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'consumo', N'Andrea Perez',      1
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'consumo', N'Carolina Gonzalez', 2
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'consumo', N'Claudia Hasbun',    2

    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'pyme',    N'Patricia Guerra',   1
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'pyme',    N'Karina Valdivia',   2
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'pyme',    N'Aylin Negrete',     3
) AS source

ON  target.periodo = source.periodo
AND target.producto = source.producto
AND target.ejecutivo = source.ejecutivo
AND target.ciclo = source.ciclo

WHEN MATCHED THEN
    UPDATE SET
        target.activo = 1

WHEN NOT MATCHED THEN
    INSERT (
        periodo,
        producto,
        ejecutivo,
        ciclo,
        activo
    )
    VALUES (
        source.periodo,
        source.producto,
        source.ejecutivo,
        source.ciclo,
        1
    );
GO


/* ----------------------------------------------------------------------------
   3) Validaciones post-carga (las tres deben devolver 0 filas)
   ---------------------------------------------------------------------------- */

-- 3.1 Ningun ejecutivo con mas de un ciclo cuando los ponderadores van al 100%
SELECT producto, ejecutivo, COUNT(*) AS ciclos
FROM dbo.sth_ejecutivos_ciclo
WHERE periodo = '2026-09-01'
  AND activo = 1
GROUP BY producto, ejecutivo
HAVING COUNT(*) > 1;

-- 3.2 Nombres que no cruzan con el carterizado del mes
--     (si no cruza, el ejecutivo desaparece del bloque en vez de dar error)
SELECT e.producto, e.ejecutivo
FROM dbo.sth_ejecutivos_ciclo e
WHERE e.periodo = '2026-09-01'
  AND e.activo = 1
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.tmp_carterizado_STH c
      WHERE CONVERT(date, c.mes_carterizado) = '2026-09-01'
        AND LTRIM(RTRIM(c.ejecutivo)) = LTRIM(RTRIM(e.ejecutivo))
  );

-- 3.3 Ciclos asignados que no tienen meta cargada en sth_metas_mensuales
SELECT DISTINCT e.producto, e.ciclo
FROM dbo.sth_ejecutivos_ciclo e
WHERE e.periodo = '2026-09-01'
  AND e.activo = 1
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.sth_metas_mensuales m
      WHERE m.periodo = e.periodo
        AND m.activo = 1
        AND m.tramo = CONCAT('Ciclo ', e.ciclo)
        -- el guion bajo evita depender de la tilde de "Contencion"
        AND m.producto LIKE CASE e.producto
                                WHEN 'hipotecario' THEN 'Contenci_n Hipotecario'
                                WHEN 'consumo'     THEN 'Contenci_n Consumo'
                                WHEN 'pyme'        THEN 'Pyme'
                                WHEN 'tarjeta'     THEN 'Tarjeta'
                            END
  );
GO
