IF OBJECT_ID('dbo.tmp_BIT_contencion', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.tmp_BIT_contencion (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        periodo CHAR(7) NOT NULL,
        fecha_carga DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        source_file NVARCHAR(260) NULL,
        rut NVARCHAR(20) NULL,
        dv NVARCHAR(5) NULL,
        con_no NVARCHAR(50) NOT NULL,
        prod NVARCHAR(100) NULL,
        tipo_prod NVARCHAR(50) NULL,
        cartera NVARCHAR(100) NULL,
        grupo_producto NVARCHAR(100) NULL,
        nombre NVARCHAR(255) NULL,
        total DECIMAL(18,2) NULL,
        dias_mora NVARCHAR(50) NULL,
        tramo_proyectado NVARCHAR(100) NULL,
        tramo_proyectado_nuevo NVARCHAR(100) NULL,
        dias_mora_hoy INT NULL,
        tramo_cierre_op NVARCHAR(100) NULL,
        dias_mora_intrames INT NULL,
        castigo INT NULL,
        paso_pc06 INT NULL,
        contiene INT NULL,
        mto_contiene DECIMAL(18,2) NULL,
        tipo_cont NVARCHAR(100) NULL
    );
    CREATE INDEX IX_tmp_BIT_contencion_periodo_conno ON dbo.tmp_BIT_contencion(periodo, con_no);
END;
GO

IF OBJECT_ID('dbo.tmp_BIT_carterizado', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.tmp_BIT_carterizado (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        periodo CHAR(7) NOT NULL,
        fecha_carga DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        source_file NVARCHAR(260) NULL,
        rut NVARCHAR(20) NULL,
        dv NVARCHAR(5) NULL,
        nro_operacion NVARCHAR(50) NOT NULL,
        usuario NVARCHAR(100) NOT NULL
    );
    CREATE INDEX IX_tmp_BIT_carterizado_periodo_operacion ON dbo.tmp_BIT_carterizado(periodo, nro_operacion);
END;
GO

IF OBJECT_ID('dbo.tmp_BIT_metas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.tmp_BIT_metas (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        periodo CHAR(7) NOT NULL,
        tramo NVARCHAR(50) NOT NULL,
        meta DECIMAL(10,6) NOT NULL
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_tmp_BIT_metas_periodo_tramo'
      AND object_id = OBJECT_ID('dbo.tmp_BIT_metas')
)
BEGIN
    CREATE UNIQUE INDEX UX_tmp_BIT_metas_periodo_tramo ON dbo.tmp_BIT_metas(periodo, tramo);
END;
GO

CREATE OR ALTER VIEW dbo.vw_BIT_data AS
WITH carterizado_unico AS (
    SELECT
        periodo,
        operation_key,
        usuario,
        ROW_NUMBER() OVER (
            PARTITION BY periodo, operation_key
            ORDER BY id ASC
        ) AS rn
    FROM (
        SELECT
            periodo,
            usuario,
            CASE
                WHEN LTRIM(RTRIM(COALESCE(nro_operacion, ''))) <> ''
                 AND LTRIM(RTRIM(COALESCE(nro_operacion, ''))) NOT LIKE '%[^0-9]%'
                    THEN CAST(CAST(LTRIM(RTRIM(nro_operacion)) AS BIGINT) AS VARCHAR(50))
                ELSE UPPER(LTRIM(RTRIM(COALESCE(nro_operacion, ''))))
            END AS operation_key,
            id
        FROM dbo.tmp_BIT_carterizado
    ) src
), dotacion AS (
    SELECT
        UPPER(LTRIM(RTRIM(usuario_ejecutivo))) AS usuario,
        nombre_ejecutivo,
        periodo_desde,
        periodo_hasta
    FROM dbo.tmp_ejecutivos
    WHERE cartera = 532
), base AS (
    SELECT
        c.periodo,
        c.rut,
        c.dv,
        c.con_no,
        COALESCE(cu.usuario, 'Phoenix') AS carterizado,
        COALESCE(d.nombre_ejecutivo, 'Phoenix') AS ejecutivo,
        CASE
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-89'
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
            ELSE ''
        END AS tramo,
        ISNULL(c.total, 0) AS mto_inicial,
        ISNULL(c.mto_contiene, 0) AS mto_contenido,
        ISNULL(c.contiene, 0) AS contiene,
        c.tipo_cont
    FROM dbo.tmp_BIT_contencion c
    LEFT JOIN carterizado_unico cu
        ON cu.periodo = c.periodo
       AND cu.operation_key = CASE
            WHEN LTRIM(RTRIM(COALESCE(c.con_no, ''))) <> ''
             AND LTRIM(RTRIM(COALESCE(c.con_no, ''))) NOT LIKE '%[^0-9]%'
                THEN CAST(CAST(LTRIM(RTRIM(c.con_no)) AS BIGINT) AS VARCHAR(50))
            ELSE UPPER(LTRIM(RTRIM(COALESCE(c.con_no, ''))))
        END
       AND cu.rn = 1
    LEFT JOIN dotacion d
        ON d.usuario = UPPER(LTRIM(RTRIM(COALESCE(cu.usuario, 'Phoenix'))))
       AND (
            d.periodo_desde IS NULL
            OR d.periodo_desde <= EOMONTH(DATEFROMPARTS(CAST(LEFT(c.periodo, 4) AS INT), CAST(RIGHT(c.periodo, 2) AS INT), 1))
       )
       AND (
            d.periodo_hasta IS NULL
            OR d.periodo_hasta >= DATEFROMPARTS(CAST(LEFT(c.periodo, 4) AS INT), CAST(RIGHT(c.periodo, 2) AS INT), 1)
       )
)
SELECT
    b.periodo,
    b.rut,
    b.dv,
    b.con_no,
    b.carterizado,
    b.ejecutivo,
    b.tramo,
    m.meta,
    CASE WHEN m.meta IS NULL THEN 0 ELSE b.mto_inicial * m.meta END AS meta_final,
    b.mto_inicial,
    b.mto_contenido,
    b.contiene,
    b.tipo_cont
FROM base b
LEFT JOIN dbo.tmp_BIT_metas m
    ON m.periodo = b.periodo
   AND m.tramo = b.tramo;
GO
