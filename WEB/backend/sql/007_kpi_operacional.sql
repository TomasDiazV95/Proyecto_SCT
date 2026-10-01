/* ============================================================
   KPI Operacional: tablas consolidadas + carga por stored procedure.

   Mandantes y segmentacion (definidos por la usuaria):
     - GM:                  bucket de mora 6-30 / 31-60 / 61-90 / 91-150.
     - SANTANDER:           producto (Hipoteca, Consumo, Pyme, TC) y ciclo
                            (Consumo C1-C2; Hipoteca y Pyme C1-C3; TC C0 y Multiciclo).
     - SC TELEFONÍA:        ciclo C1 / C2 / C3.
     - BANCO INTERNACIONAL: Vigente (30-90 / 90+) y Castigo.
     - SC TERRENO:          C3, Susc. CV, C5, C6, Pre Castigo, Castigo + zona Norte / Metropolitana / Sur.
     - ITAÚ:                Castigo (Stock / MCV) y Vencida (Consumo / Hipoteca, Fase 4-7).
     - LA ARAUCANA:         Vigente, Castigo, +365.
   Solo se cargan los segmentos definidos; el resto de la asignacion queda fuera del KPI.

   Reglas de negocio:
     - Caso = RUT unico; las operaciones son dato secundario.
     - Asignacion del periodo = la final del mes (GM: todas las operaciones asignadas en el mes).
     - Saldo asignado y pagos: los mismos montos que usa la productividad de cada cartera
       (contencion en carteras vigentes / en mora; recupero en castigos).
     - Pagos se guardan como foto diaria (kpi_pagos_diario) para comparar meses al mismo dia de avance.
       Fuentes con fecha de pago (GM, Itau Castigo, La Araucana) guardan la ultima foto y el dashboard
       corta por fecha_pago. kpi_pagos queda con la ultima foto del mes.
     - Gestiones: solo dbo.tmp_GEST_CRM.
     - Fecha de cada foto: Itau Vencida = fecha de carga; SC = fld_FECHA; Santander = fecha del nombre del archivo
       (en tmp_bench_STH la fecha_carga no es confiable: hay archivos cargados con otra fecha o en partes).

   Uso:
     EXEC dbo.sp_kpi_operacional_cargar;                      -- mes actual y 3 anteriores
     EXEC dbo.sp_kpi_operacional_cargar @periodo = '2026-09';  -- un periodo

   Nota: la base esta en nivel de compatibilidad 100: no usar TRY_CONVERT ni IIF (TRY_CAST si).
   El script es idempotente: se puede volver a ejecutar completo.
   ============================================================ */

/* ------------------------------------------------------------
   Tablas
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.kpi_crm_cartera', 'U') IS NULL
CREATE TABLE dbo.kpi_crm_cartera (
    crm_cartera INT NOT NULL PRIMARY KEY,
    mandante NVARCHAR(60) NOT NULL,
    cartera NVARCHAR(60) NULL,          -- NULL = aplica a todas las carteras del mandante
    descripcion NVARCHAR(120) NULL
);
GO

IF OBJECT_ID('dbo.kpi_tipo_contacto', 'U') IS NULL
CREATE TABLE dbo.kpi_tipo_contacto (
    valor NVARCHAR(200) NOT NULL PRIMARY KEY,
    tipo NVARCHAR(20) NOT NULL
        CONSTRAINT CK_kpi_tipo_contacto_tipo CHECK (tipo IN ('DIRECTO', 'INDIRECTO', 'SIN CONTACTO', 'EXCLUIR'))
);
GO

IF OBJECT_ID('dbo.kpi_asignacion', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.kpi_asignacion (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        periodo CHAR(7) NOT NULL,
        mandante NVARCHAR(60) NOT NULL,
        cartera NVARCHAR(60) NOT NULL,
        rut BIGINT NOT NULL,
        operacion NVARCHAR(40) NULL,
        producto NVARCHAR(100) NULL,
        tramo NVARCHAR(50) NULL,
        zona NVARCHAR(40) NULL,
        saldo_asignado DECIMAL(38,2) NULL,
        fecha_corte DATE NULL,
        source_file NVARCHAR(260) NULL
    );
    CREATE INDEX IX_kpi_asignacion_periodo ON dbo.kpi_asignacion(periodo, mandante, cartera) INCLUDE (rut, tramo, producto, saldo_asignado);
    CREATE INDEX IX_kpi_asignacion_rut ON dbo.kpi_asignacion(periodo, mandante, rut);
END;
GO

IF COL_LENGTH('dbo.kpi_asignacion', 'zona') IS NULL
    ALTER TABLE dbo.kpi_asignacion ADD zona NVARCHAR(40) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_kpi_asignacion_operacion' AND object_id = OBJECT_ID('dbo.kpi_asignacion'))
    CREATE INDEX IX_kpi_asignacion_operacion ON dbo.kpi_asignacion(periodo, mandante, operacion) INCLUDE (cartera, tramo, producto, zona);
GO

-- Ultima foto de pagos del mes (compatibilidad; el dashboard lee kpi_pagos_diario).
IF OBJECT_ID('dbo.kpi_pagos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.kpi_pagos (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        periodo CHAR(7) NOT NULL,
        mandante NVARCHAR(60) NOT NULL,
        cartera NVARCHAR(60) NOT NULL,
        rut BIGINT NOT NULL,
        operacion NVARCHAR(40) NULL,
        producto NVARCHAR(100) NULL,
        tramo NVARCHAR(50) NULL,
        monto DECIMAL(38,2) NOT NULL,
        tipo_monto NVARCHAR(20) NOT NULL,   -- CONTENCION | RECUPERO
        pago_efectivo BIT NOT NULL,         -- hubo pago real (para cumplimiento de compromisos)
        fecha_pago DATE NULL,
        fecha_corte DATE NULL,
        source_file NVARCHAR(260) NULL
    );
    CREATE INDEX IX_kpi_pagos_periodo ON dbo.kpi_pagos(periodo, mandante, cartera) INCLUDE (rut, tramo, producto, monto);
END;
GO

-- Foto diaria de pagos: una foto por fuente y dia de carga (fecha_foto).
IF OBJECT_ID('dbo.kpi_pagos_diario', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.kpi_pagos_diario (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        periodo CHAR(7) NOT NULL,
        fuente NVARCHAR(40) NOT NULL,       -- archivo de origen (una foto por fuente y dia)
        fecha_foto DATE NOT NULL,
        mandante NVARCHAR(60) NOT NULL,
        cartera NVARCHAR(60) NULL,
        rut BIGINT NOT NULL,
        operacion NVARCHAR(40) NULL,
        producto NVARCHAR(100) NULL,
        tramo NVARCHAR(50) NULL,
        zona NVARCHAR(40) NULL,
        monto DECIMAL(38,2) NOT NULL,
        tipo_monto NVARCHAR(20) NOT NULL,   -- CONTENCION | RECUPERO
        pago_efectivo BIT NOT NULL,
        fecha_pago DATE NULL,               -- si la fuente la trae, el dashboard corta por esta fecha
        source_file NVARCHAR(260) NULL
    );
    CREATE INDEX IX_kpi_pagos_diario_foto ON dbo.kpi_pagos_diario(periodo, fuente, fecha_foto)
        INCLUDE (mandante, cartera, rut, tramo, producto, zona, monto, pago_efectivo, fecha_pago);
    CREATE INDEX IX_kpi_pagos_diario_operacion ON dbo.kpi_pagos_diario(periodo, mandante, operacion);
END;
GO

IF OBJECT_ID('dbo.kpi_gestiones_rut', 'U') IS NULL
CREATE TABLE dbo.kpi_gestiones_rut (
    periodo CHAR(7) NOT NULL,
    crm_cartera INT NOT NULL,
    rut BIGINT NOT NULL,
    n_gestiones INT NOT NULL,
    tipo_contacto NVARCHAR(20) NOT NULL,
    fecha_primera_gestion DATE NULL,
    fecha_primer_directo DATE NULL,
    fecha_primer_indirecto DATE NULL,
    CONSTRAINT PK_kpi_gestiones_rut PRIMARY KEY (periodo, crm_cartera, rut)
);
GO

IF COL_LENGTH('dbo.kpi_gestiones_rut', 'n_llamadas') IS NULL
    ALTER TABLE dbo.kpi_gestiones_rut ADD n_llamadas INT NULL;
GO

-- Canal de cada AccionGestion del CRM (kpi_gestiones_rut.n_llamadas). La intensidad del dashboard usa n_gestiones (todos los canales).
IF OBJECT_ID('dbo.kpi_accion_canal', 'U') IS NULL
CREATE TABLE dbo.kpi_accion_canal (
    valor NVARCHAR(200) NOT NULL PRIMARY KEY,
    canal NVARCHAR(20) NOT NULL
        CONSTRAINT CK_kpi_accion_canal_canal CHECK (canal IN ('LLAMADA', 'IVR', 'TERRENO', 'MENSAJE', 'OTRO'))
);
GO

IF OBJECT_ID('dbo.kpi_compromisos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.kpi_compromisos (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        periodo CHAR(7) NOT NULL,
        crm_cartera INT NOT NULL,
        rut BIGINT NOT NULL,
        fecha_gestion DATETIME2(0) NOT NULL,
        fecha_compromiso DATE NULL,
        monto_compromiso DECIMAL(38,2) NULL,
        n_operaciones INT NOT NULL
    );
    CREATE INDEX IX_kpi_compromisos_periodo ON dbo.kpi_compromisos(periodo, crm_cartera, rut);
END;
GO

/* ------------------------------------------------------------
   Catalogos (solo agrega lo que falta; lo editado a mano se respeta)
   ------------------------------------------------------------ */
INSERT INTO dbo.kpi_crm_cartera (crm_cartera, mandante, cartera, descripcion)
SELECT v.crm_cartera, v.mandante, v.cartera, v.descripcion
FROM (VALUES
    (523, N'ITAÚ', N'VENCIDA', N'ITAU VENCIDA'),
    (522, N'ITAÚ', N'CASTIGO', N'ITAU CASTIGO'),
    (532, N'BANCO INTERNACIONAL', NULL, N'BANCO INTERNACIONAL'),
    (520, N'GM', NULL, N'GM'),
    (525, N'SC TERRENO', NULL, N'SC CONSUMER TERRENO'),
    (526, N'SC TELEFONÍA', NULL, N'SC TELEFONIA'),
    (527, N'SC TELEFONÍA', NULL, N'SC TELEFONIA'),
    (530, N'SANTANDER', NULL, N'SANTANDER'),
    (531, N'LA ARAUCANA', NULL, N'LA ARAUCANA')
) v (crm_cartera, mandante, cartera, descripcion)
WHERE NOT EXISTS (SELECT 1 FROM dbo.kpi_crm_cartera k WHERE k.crm_cartera = v.crm_cartera);
GO

-- Propuesta inicial de tipos de contacto; se corrige directamente en esta tabla.
INSERT INTO dbo.kpi_tipo_contacto (valor, tipo)
SELECT v.valor, v.tipo
FROM (VALUES
    (N'TITULAR', N'DIRECTO'), (N'CONTACTO DIRECTO', N'DIRECTO'), (N'CONTACTO TITULAR', N'DIRECTO'),
    (N'DIRECTO', N'DIRECTO'), (N'CONTACTO_VALIDO', N'DIRECTO'), (N'CONTACTADO', N'DIRECTO'),
    (N'CON COMPROMISO DE PAGO', N'DIRECTO'), (N'SIN COMPROMISO DE PAGO', N'DIRECTO'),
    (N'LE INTERESA', N'DIRECTO'), (N'NO LE INTERESA', N'DIRECTO'), (N'INBOUND', N'DIRECTO'),
    (N'CONTACTO TERCERO', N'INDIRECTO'), (N'CONTACTO_TERCERO', N'INDIRECTO'), (N'TERCEROS', N'INDIRECTO'),
    (N'CONTACTO INDIRECTO', N'INDIRECTO'), (N'INDIRECTO', N'INDIRECTO'), (N'AVAL', N'INDIRECTO'),
    (N'EJECUTIVO DE CUENTA', N'INDIRECTO'),
    (N'SIN CONTACTO', N'SIN CONTACTO'), (N'SIN_CONTACTO', N'SIN CONTACTO'), (N'SINCONT', N'SIN CONTACTO'),
    (N'NO CONTACTADO', N'SIN CONTACTO'), (N'SIN CONTACTO TITULAR', N'SIN CONTACTO'),
    (N'TELEFONO NO CONTESTA', N'SIN CONTACTO'), (N'NO CONTESTA', N'SIN CONTACTO'),
    (N'EQUIVOCADO', N'SIN CONTACTO'), (N'TELEFONO ERRONEO', N'SIN CONTACTO'), (N'GESTION DISCADOR', N'SIN CONTACTO'),
    (N'ENVIADO', N'EXCLUIR'), (N'MENSJ/MAIL ENVIADO', N'EXCLUIR'), (N'IVR ENVIADO', N'EXCLUIR'),
    (N'EMAIL', N'EXCLUIR'), (N'WHATSAPP', N'EXCLUIR'), (N'ENVIO WHATSAPP', N'EXCLUIR'), (N'ENVIO MAIL', N'EXCLUIR'),
    (N'INFORMATIVO', N'EXCLUIR'), (N'SEGUIMIENTO', N'EXCLUIR'), (N'PENDIENTE', N'EXCLUIR'), (N'ERROR', N'EXCLUIR'),
    (N'(VACIO)', N'EXCLUIR')
) v (valor, tipo)
WHERE NOT EXISTS (SELECT 1 FROM dbo.kpi_tipo_contacto t WHERE t.valor = v.valor);
GO

-- Canales de AccionGestion; los valores no catalogados no cuentan como llamado.
INSERT INTO dbo.kpi_accion_canal (valor, canal)
SELECT v.valor, v.canal
FROM (VALUES
    (N'GESTION DISCADOR', N'LLAMADA'), (N'TELEFONICA', N'LLAMADA'), (N'TELEFONIA', N'LLAMADA'),
    (N'TELEFONICO', N'LLAMADA'), (N'TELEFONICO-OUTBOUND', N'LLAMADA'), (N'TELEFONICO-INBOUND', N'LLAMADA'),
    (N'TELEFONIA INBOUND', N'LLAMADA'), (N'INBOUND', N'LLAMADA'),
    (N'SIN CONTACTO', N'LLAMADA'), (N'CONTACTO TITULAR', N'LLAMADA'), (N'CONTACTO TERCERO', N'LLAMADA'),
    (N'TELEFONICO-IVR', N'IVR'),
    (N'TERRENO', N'TERRENO'), (N'PRESENCIAL', N'TERRENO'),
    (N'MAIL', N'MENSAJE'), (N'EMAIL', N'MENSAJE'), (N'SMS', N'MENSAJE'), (N'WHATSAPP', N'MENSAJE'), (N'WHATSAPP-INBOUND', N'MENSAJE'),
    (N'GESTION ADMINISTRATIVA', N'OTRO'), (N'ENCUESTA', N'OTRO')
) v (valor, canal)
WHERE NOT EXISTS (SELECT 1 FROM dbo.kpi_accion_canal a WHERE a.valor = v.valor);
GO

/* ------------------------------------------------------------
   Carga de un periodo
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.sp_kpi_operacional_cargar_periodo', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_kpi_operacional_cargar_periodo;
GO

CREATE PROCEDURE dbo.sp_kpi_operacional_cargar_periodo
    @periodo CHAR(7)   -- 'YYYY-MM'
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @periodo IS NULL OR @periodo NOT LIKE '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
    BEGIN
        RAISERROR('Periodo invalido: %s. Se esperaba YYYY-MM', 16, 1, @periodo);
        RETURN;
    END;

    DECLARE @inicio DATE = CAST(REPLACE(@periodo, '-', '') + '01' AS date);
    DECLARE @fin DATE = DATEADD(MONTH, 1, @inicio);
    DECLARE @periodo_yyyymm CHAR(6) = REPLACE(@periodo, '-', '');
    DECLARE @periodo_mmyyyy CHAR(7) = RIGHT(@periodo, 2) + '-' + LEFT(@periodo, 4);

    DECLARE @stats TABLE (paso NVARCHAR(40), filas INT);

    -- Ultimo archivo de contencion Itau Vencida del mes (base del tramo).
    DECLARE @contencion_itv NVARCHAR(260), @contencion_itv_fecha DATE;
    SELECT TOP (1) @contencion_itv = source_file, @contencion_itv_fecha = fecha_carga
    FROM dbo.contencion_itau_vencida
    WHERE fecha_carga >= @inicio AND fecha_carga < @fin
    GROUP BY source_file, fecha_carga
    ORDER BY fecha_carga DESC, MAX(ts_carga) DESC;

    -- Ultimo archivo de recupero Itau Castigo del mes (hay dias con dos cargas).
    DECLARE @recup_itc NVARCHAR(260), @recup_itc_fecha DATE;
    SELECT TOP (1) @recup_itc = source_file, @recup_itc_fecha = fecha_carga
    FROM dbo.recup_itau_castigo
    WHERE fecha_carga >= @inicio AND fecha_carga < @fin
    GROUP BY source_file, fecha_carga
    ORDER BY fecha_carga DESC, MAX(ts_carga) DESC;

    -- Ultima asignacion diaria Itau Vencida del mes (fecha en el nombre del archivo).
    DECLARE @asig_itv NVARCHAR(260), @asig_itv_fecha DATE;
    SELECT TOP (1) @asig_itv = source_file, @asig_itv_fecha = fecha_archivo
    FROM (
        SELECT DISTINCT source_file,
               TRY_CAST(SUBSTRING(source_file, PATINDEX('%[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]%', source_file), 8) AS date) AS fecha_archivo
        FROM dbo.asignacion_itau_vencida
    ) archivos
    WHERE fecha_archivo >= @inicio AND fecha_archivo < @fin
    ORDER BY fecha_archivo DESC, source_file DESC;

    -- Ultima asignacion La Araucana del mes.
    DECLARE @la_fecha DATE;
    SELECT @la_fecha = MAX(fecha_carga) FROM dbo.tmp_LA_asignacion WHERE periodo = @periodo_mmyyyy;

    DECLARE @la_pagos_fecha DATE;
    SELECT @la_pagos_fecha = MAX(fecha_carga) FROM dbo.tmp_LA_pagos WHERE periodo = @periodo_mmyyyy;

    -- Fotos diarias de los bench: una por dia de datos (fecha_foto), con el archivo y la carga que la forman.
    -- fecha_carga NULL = todas las cargas del archivo (Santander llega partido en varias cargas).
    CREATE TABLE #fotos (
        fuente NVARCHAR(40) NOT NULL,
        fecha_foto DATE NOT NULL,
        source_file NVARCHAR(260) NOT NULL,
        fecha_carga DATE NULL
    );

    -- Itau Vencida: la fecha de carga es la del archivo; el ultimo archivo de cada dia.
    INSERT INTO #fotos (fuente, fecha_foto, source_file, fecha_carga)
    SELECT 'ITV_CONTENCION', fecha_carga, source_file, fecha_carga
    FROM (
        SELECT fecha_carga, source_file,
               ROW_NUMBER() OVER (PARTITION BY fecha_carga ORDER BY MAX(ts_carga) DESC, source_file DESC) AS rn
        FROM dbo.contencion_itau_vencida
        WHERE fecha_carga >= @inicio AND fecha_carga < @fin
        GROUP BY fecha_carga, source_file
    ) f WHERE rn = 1;

    -- Santander: la fecha_carga no es confiable (archivos cargados con otra fecha o en partes); la fecha de la foto
    -- sale del nombre ('seguimiento al DD-MM' / 'al DDMM'; 'cierre' = fin de mes). Se descartan los archivos 'prueba'.
    -- Si hay dos archivos del mismo dia, el con mas operaciones.
    ;WITH f AS (
        SELECT source_file, LOWER(source_file) AS nombre, MAX(fecha_carga) AS fc, MAX(ts_carga) AS ts,
               COUNT(DISTINCT fld_Operaciones) AS ops
        FROM dbo.tmp_bench_STH
        GROUP BY source_file
    ),
    p AS (
        SELECT f.*,
               PATINDEX('% al [0-9][0-9]-[0-9][0-9]%', nombre) AS i1,
               PATINDEX('% al [0-9][0-9][0-9][0-9]%', nombre) AS i2
        FROM f
        WHERE nombre NOT LIKE '%prueba%'
    ),
    d AS (
        SELECT p.*,
               CASE WHEN i1 > 0 THEN SUBSTRING(nombre, i1 + 4, 2) WHEN i2 > 0 THEN SUBSTRING(nombre, i2 + 4, 2) END AS dd,
               CASE WHEN i1 > 0 THEN SUBSTRING(nombre, i1 + 7, 2) WHEN i2 > 0 THEN SUBSTRING(nombre, i2 + 6, 2) END AS mm
        FROM p
    ),
    e AS (
        SELECT d.*,
               CASE
                   WHEN dd IS NOT NULL THEN TRY_CAST(
                       CAST(YEAR(fc) + CASE WHEN CAST(mm AS int) - MONTH(fc) > 6 THEN -1
                                            WHEN MONTH(fc) - CAST(mm AS int) > 6 THEN 1 ELSE 0 END AS char(4)) + mm + dd AS date)
                   WHEN nombre LIKE '%cierre%' THEN EOMONTH(fc)
                   ELSE fc
               END AS fecha_foto
        FROM d
    ),
    r AS (
        SELECT e.*, ROW_NUMBER() OVER (PARTITION BY fecha_foto ORDER BY ops DESC, ts DESC) AS rn
        FROM e
        WHERE fecha_foto >= @inicio AND fecha_foto < @fin
    )
    INSERT INTO #fotos (fuente, fecha_foto, source_file, fecha_carga)
    SELECT 'STH_BENCH', fecha_foto, source_file, NULL
    FROM r WHERE rn = 1;

    -- SC Terreno y SC Telefonia: periodo = fld_PERIODO (los primeros dias del mes llega el cierre del anterior) y
    -- fecha de la foto = fld_FECHA. Un archivo recargado se toma de su ultima carga.
    INSERT INTO #fotos (fuente, fecha_foto, source_file, fecha_carga)
    SELECT 'STC_BENCH', fecha_foto, source_file, fc
    FROM (
        SELECT source_file, MAX(fecha_carga) AS fc,
               ISNULL(TRY_CAST(MAX(fld_FECHA) AS date), MAX(fecha_carga)) AS fecha_foto,
               ROW_NUMBER() OVER (PARTITION BY ISNULL(TRY_CAST(MAX(fld_FECHA) AS date), MAX(fecha_carga))
                                  ORDER BY MAX(ts_carga) DESC, source_file DESC) AS rn
        FROM dbo.tmp_bench_STC
        WHERE fld_PERIODO = @periodo_yyyymm
        GROUP BY source_file
    ) f WHERE rn = 1;

    INSERT INTO #fotos (fuente, fecha_foto, source_file, fecha_carga)
    SELECT 'TEL_BENCH', fecha_foto, source_file, fc
    FROM (
        SELECT source_file, MAX(fecha_carga) AS fc,
               ISNULL(TRY_CAST(MAX(fld_FECHA) AS date), MAX(fecha_carga)) AS fecha_foto,
               ROW_NUMBER() OVER (PARTITION BY ISNULL(TRY_CAST(MAX(fld_FECHA) AS date), MAX(fecha_carga))
                                  ORDER BY MAX(ts_carga) DESC, source_file DESC) AS rn
        FROM dbo.tmp_bench_temp_STC
        WHERE fld_PERIODO = @periodo_yyyymm
        GROUP BY source_file
    ) f WHERE rn = 1;

    -- Asignacion final de los bench = ultima foto del mes.
    DECLARE @sth_file NVARCHAR(260), @sth_fecha DATE;
    SELECT TOP (1) @sth_file = source_file, @sth_fecha = fecha_foto FROM #fotos WHERE fuente = 'STH_BENCH' ORDER BY fecha_foto DESC;

    DECLARE @stc_file NVARCHAR(260), @stc_carga DATE, @stc_fecha DATE;
    SELECT TOP (1) @stc_file = source_file, @stc_carga = fecha_carga, @stc_fecha = fecha_foto FROM #fotos WHERE fuente = 'STC_BENCH' ORDER BY fecha_foto DESC;

    DECLARE @tel_file NVARCHAR(260), @tel_carga DATE, @tel_fecha DATE;
    SELECT TOP (1) @tel_file = source_file, @tel_carga = fecha_carga, @tel_fecha = fecha_foto FROM #fotos WHERE fuente = 'TEL_BENCH' ORDER BY fecha_foto DESC;

    BEGIN TRANSACTION;

    DELETE FROM dbo.kpi_asignacion WHERE periodo = @periodo;
    DELETE FROM dbo.kpi_pagos WHERE periodo = @periodo;
    DELETE FROM dbo.kpi_pagos_diario WHERE periodo = @periodo;
    DELETE FROM dbo.kpi_gestiones_rut WHERE periodo = @periodo;
    DELETE FROM dbo.kpi_compromisos WHERE periodo = @periodo;

    /* ================= Asignacion ================= */

    -- Itau Vencida: fase de la contencion Phoenix del mes (como en productividad Itau Vencida).
    -- Solo Consumo e Hipoteca en Fase 4 a 7.
    ;WITH cont AS (
        SELECT OPER, MAX(CAST(FASE_PROY_MAX AS int)) AS fase
        FROM dbo.contencion_itau_vencida
        WHERE source_file = @contencion_itv AND fecha_carga = @contencion_itv_fecha AND GESTOR = 'PHOENIX'
        GROUP BY OPER
    ),
    base AS (
        SELECT a.*, c.fase,
               CASE LTRIM(RTRIM(a.Producto))
                   WHEN 'Credito Consumo' THEN N'Consumo'
                   WHEN 'Hipotecario' THEN N'Hipoteca'
               END AS producto_kpi
        FROM dbo.asignacion_itau_vencida a
        INNER JOIN cont c ON c.OPER = a.Numero_Cuenta
        WHERE a.source_file = @asig_itv AND a.Rut IS NOT NULL
    )
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'ITAÚ', N'VENCIDA', CAST(b.Rut AS bigint), b.Numero_Cuenta, b.producto_kpi,
           CONCAT('Fase ', b.fase), b.Monto_Asignado, @asig_itv_fecha, b.source_file
    FROM base b
    WHERE b.producto_kpi IS NOT NULL AND b.fase BETWEEN 4 AND 7;
    INSERT INTO @stats VALUES ('asig_itau_vencida', @@ROWCOUNT);

    -- Itau Castigo: un periodo por archivo (el ETL deja solo la ultima del mes). Stock = Phoenix, MCV = Phoenix MCV.
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'ITAÚ', N'CASTIGO', CAST(a.RUT AS bigint), NULL, NULL,
           CASE UPPER(LTRIM(RTRIM(a.COBRADOR_VISTA))) WHEN 'PHOENIX' THEN N'Stock' WHEN 'PHOENIX MCV' THEN N'MCV' END,
           a.SDO_CAST_ACTUAL, a.fecha_carga, a.source_file
    FROM dbo.tmp_itau_castigo_asignacion a
    WHERE a.PERIODO = @periodo_yyyymm AND a.RUT IS NOT NULL
      AND UPPER(LTRIM(RTRIM(a.COBRADOR_VISTA))) IN ('PHOENIX', 'PHOENIX MCV');
    INSERT INTO @stats VALUES ('asig_itau_castigo', @@ROWCOUNT);

    -- BIT: solo carteras Vigente y Castigo (no existe Vencida). 'CARTERA MORA 30-89' y 'CARTERA VENCIDA' son Vigente,
    -- abierta en tramos 30-90 / 90+ desde la contencion (T1-T3 / T4-T7) como en productividad BIT.
    ;WITH cont AS (
        SELECT TRY_CAST(con_no AS bigint) AS op, MAX(LEFT(tramo_proyectado_nuevo, 2)) AS t
        FROM dbo.tmp_BIT_contencion
        WHERE periodo = @periodo
        GROUP BY TRY_CAST(con_no AS bigint)
    ),
    base AS (
        SELECT a.*,
               CASE
                   WHEN UPPER(a.CAMPANA) LIKE 'CASTIGO%' THEN 'CASTIGO'
                   WHEN UPPER(a.CAMPANA) LIKE '%MORA%' OR UPPER(a.CAMPANA) LIKE '%VENCIDA%' THEN 'VIGENTE'
               END AS cartera_kpi
        FROM dbo.tmp_BIT_asignacion a
        WHERE a.periodo = @periodo
    )
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'BANCO INTERNACIONAL', b.cartera_kpi, TRY_CAST(b.RUT AS bigint), b.NRO_OPERACION,
           CASE WHEN UPPER(b.GRUPO_PRODUCTO) IN ('TARJETA', 'TARJETAS') THEN 'Tarjetas' ELSE NULLIF(LTRIM(RTRIM(b.GRUPO_PRODUCTO)), '') END,
           CASE
               WHEN b.cartera_kpi = 'CASTIGO' THEN 'Castigo'
               WHEN c.t IN ('T1', 'T2', 'T3') THEN '30-90'
               WHEN c.t IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
               -- Sin tramo en la contencion: segun la campana.
               WHEN UPPER(b.CAMPANA) LIKE '%VENCIDA%' THEN '90+'
               ELSE '30-90'
           END,
           b.DEUDA_TOTAL, TRY_CAST(b.fecha_carga AS date), b.source_file
    FROM base b
    LEFT JOIN cont c ON c.op = TRY_CAST(b.NRO_OPERACION AS bigint)
    WHERE TRY_CAST(b.RUT AS bigint) IS NOT NULL AND b.cartera_kpi IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_bit', @@ROWCOUNT);

    -- GM: todas las operaciones asignadas en el mes, con su primera aparicion (como en productividad GM).
    ;WITH base AS (
        SELECT g.*,
               ROW_NUMBER() OVER (PARTITION BY g.[fld_Agreement Number] ORDER BY g.fecha_carga ASC, g.ts_carga ASC) AS rn
        FROM dbo.tmp_asig_GM g
        WHERE g.fecha_carga >= @inicio AND g.fecha_carga < @fin
    )
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'GM', N'GM',
           TRY_CAST(LEFT(b.[fld_National Id], CHARINDEX('-', b.[fld_National Id] + '-') - 1) AS bigint),
           b.[fld_Agreement Number], NULL,
           REPLACE(LTRIM(RTRIM(b.fld_bucket)), ' a ', '-'),
           b.[fld_POS/Curr. Acc. Bal.* ], b.fecha_carga, b.source_file
    FROM base b
    WHERE b.rn = 1
      AND LTRIM(RTRIM(b.fld_bucket)) IN ('6 a 30', '31 a 60', '61 a 90', '91 a 150')
      AND TRY_CAST(LEFT(b.[fld_National Id], CHARINDEX('-', b.[fld_National Id] + '-') - 1) AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_gm', @@ROWCOUNT);

    -- Santander: producto = empresa Phoenix; ciclos de cada producto como en productividad STH.
    ;WITH base AS (
        SELECT b.*,
               CASE UPPER(LTRIM(RTRIM(b.fld_Empresa)))
                   WHEN 'PHOENIX CONSUMO' THEN N'Consumo'
                   WHEN 'PHOENIX HIPOTECARIO' THEN N'Hipoteca'
                   WHEN 'PHOENIX PYME' THEN N'Pyme'
                   WHEN 'PHOENIX TC' THEN N'TC'
               END AS producto_kpi,
               TRY_CAST(b.fld_Ciclo AS int) AS ciclo,
               ROW_NUMBER() OVER (PARTITION BY b.fld_Operaciones ORDER BY b.fecha_carga DESC, b.ts_carga DESC) AS rn
        FROM dbo.tmp_bench_STH b
        WHERE b.source_file = @sth_file
    ),
    seg AS (
        SELECT base.*,
               CASE
                   WHEN producto_kpi = N'TC' AND ciclo = 0 THEN 'C0'
                   WHEN producto_kpi = N'TC' AND ciclo BETWEEN 1 AND 6 THEN 'Multiciclo'
                   WHEN producto_kpi = N'Consumo' AND ciclo IN (1, 2) THEN CONCAT('C', ciclo)
                   WHEN producto_kpi IN (N'Hipoteca', N'Pyme') AND ciclo IN (1, 2, 3) THEN CONCAT('C', ciclo)
               END AS tramo_kpi
        FROM base
        WHERE rn = 1
    )
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'SANTANDER', s.producto_kpi, TRY_CAST(s.fld_Rut AS bigint), s.fld_Operaciones, s.producto_kpi,
           s.tramo_kpi, s.[fld_MM$ Monto], @sth_fecha, s.source_file
    FROM seg s
    WHERE s.tramo_kpi IS NOT NULL AND TRY_CAST(s.fld_Rut AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_santander', @@ROWCOUNT);

    -- SC Telefonia: ciclos C1-C3 (como en productividad SC Temprana).
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'SC TELEFONÍA', N'TELEFONÍA', TRY_CAST(b.fld_RUT AS bigint), b.fld_OPERACION, NULL,
           UPPER(LTRIM(RTRIM(b.fld_TRAMO_MORA))), b.fld_DEUDA_INI, @tel_fecha, b.source_file
    FROM dbo.tmp_bench_temp_STC b
    WHERE b.source_file = @tel_file AND b.fecha_carga = @tel_carga
      AND UPPER(LTRIM(RTRIM(b.fld_TRAMO_MORA))) IN ('C1', 'C2', 'C3')
      AND TRY_CAST(b.fld_RUT AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_sc_telefonia', @@ROWCOUNT);

    -- SC Terreno: segmento segun tramo y apertura (regla _general_bucket de productividad SC) + castigo F1-F4.
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, zona, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'SC TERRENO', N'TERRENO', s.rut, s.fld_OPERACION, NULL, s.segmento, s.zona, s.fld_DEUDA_INI, @stc_fecha, s.source_file
    FROM (
        SELECT b.*, TRY_CAST(b.fld_RUT AS bigint) AS rut,
               CASE
                   WHEN t.tramo IN ('C6', 'C7', 'C8') AND t.apertura = 'SUSCEPTIBLE CASTIGO' THEN N'Pre Castigo'
                   WHEN t.tramo = 'C6' THEN N'C6'
                   WHEN t.tramo = 'C3' THEN N'C3'
                   WHEN t.apertura = 'SUSCEPTIBLE CV' THEN N'Susc. CV'
                   WHEN t.tramo = 'C5' THEN N'C5'
                   WHEN t.tramo IN ('F1', 'F2', 'F3', 'F4') THEN N'Castigo'
               END AS segmento,
               CASE UPPER(LTRIM(RTRIM(b.fld_ZONA)))
                   WHEN 'ZONA NORTE CENTRO' THEN N'Norte'
                   WHEN 'ZONA METROPOLITANA' THEN N'Metropolitana'
                   WHEN 'ZONA CENTRO SUR' THEN N'Sur'
                   ELSE NULLIF(LTRIM(RTRIM(b.fld_ZONA)), '')
               END AS zona
        FROM dbo.tmp_bench_STC b
        CROSS APPLY (SELECT UPPER(LTRIM(RTRIM(b.fld_TRAMO_MORA))) AS tramo, UPPER(LTRIM(RTRIM(b.fld_APERTURA))) AS apertura) t
        WHERE b.source_file = @stc_file AND b.fecha_carga = @stc_carga
    ) s
    WHERE s.segmento IS NOT NULL AND s.rut IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_sc_terreno', @@ROWCOUNT);

    -- La Araucana: cartera = tipo de cartera (Vigente / Castigo / +365).
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'LA ARAUCANA', c.cartera, TRY_CAST(a.fld_RUT_ASIGNADO AS bigint), a.fld_FOLIO_CREDITO, NULL,
           c.cartera, a.fld_TOTAL_DEUDA, a.fecha_carga, a.source_file
    FROM dbo.tmp_LA_asignacion a
    CROSS APPLY (
        SELECT CASE UPPER(LTRIM(RTRIM(a.fld_TIPO_CARTERA)))
                   WHEN 'VIGENTE' THEN N'VIGENTE'
                   WHEN 'CASTIGO' THEN N'CASTIGO'
                   WHEN '+365' THEN N'+365'
                   WHEN '365' THEN N'+365'
               END AS cartera
    ) c
    WHERE a.periodo = @periodo_mmyyyy AND a.fecha_carga = @la_fecha
      AND c.cartera IS NOT NULL AND TRY_CAST(a.fld_RUT_ASIGNADO AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_la_araucana', @@ROWCOUNT);

    /* ================= Pagos (foto diaria) ================= */

    -- Itau Vencida: contencion (SALDO_CONT) de cada foto diaria del mes, solo GESTOR PHOENIX.
    -- Pago efectivo = operacion contenida (como en las demas carteras de contencion); EFECT_RECUPERADO no viene
    -- informado en todos los archivos.
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, f.fuente, f.fecha_foto, N'ITAÚ', N'VENCIDA', CAST(c.RUT AS bigint), c.OPER, ISNULL(c.SALDO_CONT, 0), 'CONTENCION',
           1, NULL, c.source_file
    FROM #fotos f
    INNER JOIN dbo.contencion_itau_vencida c ON c.source_file = f.source_file AND c.fecha_carga = f.fecha_carga
    WHERE f.fuente = 'ITV_CONTENCION'
      AND c.GESTOR = 'PHOENIX' AND c.RUT IS NOT NULL
      AND (ISNULL(c.SALDO_CONT, 0) > 0 OR ISNULL(c.EFECT_RECUPERADO, 0) > 0);
    INSERT INTO @stats VALUES ('pagos_itau_vencida', @@ROWCOUNT);

    -- Itau Castigo: recupero del ultimo archivo del mes; se corta por FECHA_RECUPERO.
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, 'ITC_RECUPERO', r.fecha_carga, N'ITAÚ', N'CASTIGO', CAST(r.RUT AS bigint), NULL, r.RECUPERO, 'RECUPERO', 1,
           TRY_CAST(r.FECHA_RECUPERO AS date), r.source_file
    FROM dbo.recup_itau_castigo r
    WHERE r.source_file = @recup_itc AND r.fecha_carga = @recup_itc_fecha
      AND r.RUT IS NOT NULL AND ISNULL(r.RECUPERO, 0) > 0;
    INSERT INTO @stats VALUES ('pagos_itau_castigo', @@ROWCOUNT);

    -- BIT Vigente: contencion (mto_contiene). Llega una foto por mes.
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, 'BIT_CONTENCION', CAST(c.fecha_carga AS date), N'BANCO INTERNACIONAL', 'VIGENTE',
           TRY_CAST(c.rut AS bigint), c.con_no, c.mto_contiene, 'CONTENCION',
           CASE WHEN c.contiene = 1 THEN 1 ELSE 0 END, NULL, c.source_file
    FROM dbo.tmp_BIT_contencion c
    WHERE c.periodo = @periodo AND TRY_CAST(c.rut AS bigint) IS NOT NULL AND ISNULL(c.mto_contiene, 0) > 0;
    INSERT INTO @stats VALUES ('pagos_bit_contencion', @@ROWCOUNT);

    -- BIT Castigo: recupero.
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, 'BIT_CASTIGO', b.fecha_carga, N'BANCO INTERNACIONAL', 'CASTIGO', TRY_CAST(b.RUT AS bigint), NULL, b.MTO_RECUPERO_FINAL, 'RECUPERO', 1,
           NULL, b.source_file
    FROM dbo.tmp_BIT_castigo b
    WHERE b.periodo = @periodo AND TRY_CAST(b.RUT AS bigint) IS NOT NULL AND ISNULL(b.MTO_RECUPERO_FINAL, 0) > 0;
    INSERT INTO @stats VALUES ('pagos_bit_castigo', @@ROWCOUNT);

    -- GM: operacion contenida en el mes = saldo asignado contenido; fecha de pago = primer dia contenido.
    ;WITH pag AS (
        SELECT operacion, MIN(periodo_pago) AS fecha_pago, MAX(CAST(fecha_carga AS date)) AS fecha_foto
        FROM dbo.tmp_pagos_gm
        WHERE periodo_pago >= @inicio AND periodo_pago < @fin AND contenido = 1
        GROUP BY operacion
    )
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, 'GM_PAGOS', (SELECT MAX(fecha_foto) FROM pag), N'GM', N'GM', a.rut, a.operacion, ISNULL(a.saldo_asignado, 0),
           'CONTENCION', 1, p.fecha_pago, NULL
    FROM pag p
    INNER JOIN dbo.kpi_asignacion a ON a.periodo = @periodo AND a.mandante = N'GM' AND a.operacion = p.operacion;
    INSERT INTO @stats VALUES ('pagos_gm', @@ROWCOUNT);

    -- Santander: operacion contenida en cada foto diaria = monto asignado de la operacion (una fila por operacion).
    ;WITH b AS (
        SELECT f.fuente, f.fecha_foto, s.*,
               ROW_NUMBER() OVER (PARTITION BY f.fecha_foto, s.fld_Operaciones ORDER BY s.fecha_carga DESC, s.ts_carga DESC) AS rn
        FROM #fotos f
        INNER JOIN dbo.tmp_bench_STH s ON s.source_file = f.source_file
        WHERE f.fuente = 'STH_BENCH'
    )
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, b.fuente, b.fecha_foto, N'SANTANDER', NULL, TRY_CAST(b.fld_Rut AS bigint), b.fld_Operaciones,
           ISNULL(b.[fld_MM$ Monto], 0), 'CONTENCION', 1, NULL, b.source_file
    FROM b
    WHERE b.rn = 1 AND TRY_CAST(b.fld_Contenido AS int) = 1 AND TRY_CAST(b.fld_Rut AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('pagos_santander', @@ROWCOUNT);

    -- SC Telefonia y SC Terreno: monto contenido de cada foto diaria.
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, f.fuente, f.fecha_foto, N'SC TELEFONÍA', NULL, TRY_CAST(b.fld_RUT AS bigint), b.fld_OPERACION,
           b.fld_CONTENIDO, 'CONTENCION', 1, NULL, b.source_file
    FROM #fotos f
    INNER JOIN dbo.tmp_bench_temp_STC b ON b.source_file = f.source_file AND b.fecha_carga = f.fecha_carga
    WHERE f.fuente = 'TEL_BENCH' AND ISNULL(b.fld_CONTENIDO, 0) > 0 AND TRY_CAST(b.fld_RUT AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('pagos_sc_telefonia', @@ROWCOUNT);

    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, f.fuente, f.fecha_foto, N'SC TERRENO', NULL, TRY_CAST(b.fld_RUT AS bigint), b.fld_OPERACION,
           b.fld_CONTENIDO, 'CONTENCION', 1, NULL, b.source_file
    FROM #fotos f
    INNER JOIN dbo.tmp_bench_STC b ON b.source_file = f.source_file AND b.fecha_carga = f.fecha_carga
    WHERE f.fuente = 'STC_BENCH' AND ISNULL(b.fld_CONTENIDO, 0) > 0 AND TRY_CAST(b.fld_RUT AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('pagos_sc_terreno', @@ROWCOUNT);

    -- La Araucana: recuperacion con los tipos de pago validos de productividad; se corta por fecha de pago.
    INSERT INTO dbo.kpi_pagos_diario (periodo, fuente, fecha_foto, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, source_file)
    SELECT @periodo, 'LA_PAGOS', p.fecha_carga, N'LA ARAUCANA',
           CASE UPPER(LTRIM(RTRIM(p.fld_TIPO_CARTERA)))
               WHEN 'CARTERA VIGENTE' THEN N'VIGENTE'
               WHEN 'CARTERA CASTIGO' THEN N'CASTIGO'
               WHEN 'CARTERA NO VIGENTE' THEN N'+365'
           END,
           TRY_CAST(LEFT(p.fld_RutAfiliado, CHARINDEX('-', p.fld_RutAfiliado + '-') - 1) AS bigint),
           p.fld_CONTRATO, p.fld_Recuperacion, 'RECUPERO', 1,
           NULLIF(CASE
               WHEN f.v LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN TRY_CAST(f.v AS date)
               WHEN f.v LIKE '[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]' THEN TRY_CAST(RIGHT(f.v, 4) + SUBSTRING(f.v, 4, 2) + LEFT(f.v, 2) AS date)
           END, '19000101'),
           p.source_file
    FROM dbo.tmp_LA_pagos p
    CROSS APPLY (SELECT LTRIM(RTRIM(p.fld_FechaPago)) AS v) f
    WHERE p.periodo = @periodo_mmyyyy AND p.fecha_carga = @la_pagos_fecha
      AND REPLACE(UPPER(LTRIM(RTRIM(p.fld_TipoPago))), ' ', '') IN ('E-ACTSEGCES', 'E-MANUAL', 'E-INTER-CC', 'E-CC')
      AND ISNULL(p.fld_Recuperacion, 0) > 0
      AND TRY_CAST(LEFT(p.fld_RutAfiliado, CHARINDEX('-', p.fld_RutAfiliado + '-') - 1) AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('pagos_la_araucana', @@ROWCOUNT);

    -- Segmento del pago: el de la asignacion por operacion y, si no, por RUT (en la misma cartera si se conoce).
    -- Sin asignacion: tramo 'Sin asignación' (no entra al KPI de pagos ni al % de recuperacion).
    ;WITH ao AS (
        SELECT mandante, operacion, MAX(cartera) AS cartera, MAX(tramo) AS tramo, MAX(producto) AS producto, MAX(zona) AS zona
        FROM dbo.kpi_asignacion
        WHERE periodo = @periodo AND operacion IS NOT NULL
        GROUP BY mandante, operacion
    )
    UPDATE p
    SET cartera = ao.cartera, tramo = ao.tramo, producto = ao.producto, zona = ao.zona
    FROM dbo.kpi_pagos_diario p
    INNER JOIN ao ON ao.mandante = p.mandante AND ao.operacion = p.operacion
    WHERE p.periodo = @periodo;

    ;WITH ar AS (
        SELECT mandante, rut, cartera, tramo, producto, zona,
               ROW_NUMBER() OVER (PARTITION BY mandante, rut ORDER BY saldo_asignado DESC) AS rn_rut,
               ROW_NUMBER() OVER (PARTITION BY mandante, cartera, rut ORDER BY saldo_asignado DESC) AS rn_cartera
        FROM dbo.kpi_asignacion
        WHERE periodo = @periodo
    )
    UPDATE p
    SET cartera = ar.cartera, tramo = ar.tramo, producto = ar.producto, zona = ar.zona
    FROM dbo.kpi_pagos_diario p
    INNER JOIN ar
        ON ar.mandante = p.mandante AND ar.rut = p.rut
       AND ((p.cartera IS NULL AND ar.rn_rut = 1) OR (p.cartera = ar.cartera AND ar.rn_cartera = 1))
    WHERE p.periodo = @periodo AND p.tramo IS NULL;

    UPDATE dbo.kpi_pagos_diario
    SET tramo = N'Sin asignación', cartera = ISNULL(cartera, N'Sin asignación')
    WHERE periodo = @periodo AND tramo IS NULL;

    -- kpi_pagos: ultima foto del mes de cada fuente.
    INSERT INTO dbo.kpi_pagos (periodo, mandante, cartera, rut, operacion, producto, tramo, monto, tipo_monto, pago_efectivo, fecha_pago, fecha_corte, source_file)
    SELECT p.periodo, p.mandante, p.cartera, p.rut, p.operacion, p.producto, p.tramo, p.monto, p.tipo_monto, p.pago_efectivo,
           p.fecha_pago, p.fecha_foto, p.source_file
    FROM dbo.kpi_pagos_diario p
    INNER JOIN (
        SELECT fuente, MAX(fecha_foto) AS fecha_foto FROM dbo.kpi_pagos_diario WHERE periodo = @periodo GROUP BY fuente
    ) u ON u.fuente = p.fuente AND u.fecha_foto = p.fecha_foto
    WHERE p.periodo = @periodo;

    /* ================= Gestiones ================= */

    -- Un registro por periodo, cartera CRM y RUT, con el mejor contacto del mes: Directo > Indirecto > Sin contacto,
    -- y la fecha del primer contacto de cada tipo (el dashboard reconstruye el contacto a cualquier dia de corte).
    -- Los valores EXCLUIR (envios masivos, etc.) no cuentan como gestion. Los no catalogados cuentan como Sin contacto.
    ;WITH g AS (
        SELECT g.cartera AS crm_cartera,
               TRY_CAST(g.rut AS bigint) AS rut,
               g.GestionFecha AS fecha,
               ISNULL(t.tipo, 'SIN CONTACTO') AS tipo,
               CASE WHEN a.canal = 'LLAMADA' THEN 1 ELSE 0 END AS es_llamada
        FROM dbo.tmp_GEST_CRM g
        INNER JOIN dbo.kpi_crm_cartera k ON k.crm_cartera = g.cartera
        LEFT JOIN dbo.kpi_tipo_contacto t
            ON t.valor = ISNULL(NULLIF(UPPER(LTRIM(RTRIM(g.ContactoGestion))), ''), '(VACIO)')
        LEFT JOIN dbo.kpi_accion_canal a
            ON a.valor = UPPER(LTRIM(RTRIM(g.AccionGestion)))
        WHERE g.GestionFecha >= @inicio AND g.GestionFecha < @fin
          AND TRY_CAST(g.rut AS bigint) IS NOT NULL
    )
    INSERT INTO dbo.kpi_gestiones_rut (periodo, crm_cartera, rut, n_gestiones, n_llamadas, tipo_contacto,
                                       fecha_primera_gestion, fecha_primer_directo, fecha_primer_indirecto)
    SELECT @periodo, crm_cartera, rut, COUNT(*), SUM(es_llamada),
           CASE
               WHEN MAX(CASE WHEN tipo = 'DIRECTO' THEN 1 ELSE 0 END) = 1 THEN 'DIRECTO'
               WHEN MAX(CASE WHEN tipo = 'INDIRECTO' THEN 1 ELSE 0 END) = 1 THEN 'INDIRECTO'
               ELSE 'SIN CONTACTO'
           END,
           MIN(fecha),
           MIN(CASE WHEN tipo = 'DIRECTO' THEN fecha END),
           MIN(CASE WHEN tipo = 'INDIRECTO' THEN fecha END)
    FROM g
    WHERE tipo <> 'EXCLUIR'
    GROUP BY crm_cartera, rut;
    INSERT INTO @stats VALUES ('gestiones_rut', @@ROWCOUNT);

    /* ================= Compromisos ================= */

    -- Un compromiso = RUT + momento de gestion + fecha comprometida (el CRM repite la fila por cada operacion).
    -- El periodo es el de la fecha en que se genero el compromiso.
    INSERT INTO dbo.kpi_compromisos (periodo, crm_cartera, rut, fecha_gestion, fecha_compromiso, monto_compromiso, n_operaciones)
    SELECT @periodo, c.cartera, TRY_CAST(c.RutCliente AS bigint), c.FechaGestion, c.FechaCompromiso,
           SUM(c.MontoCompromiso), COUNT(*)
    FROM dbo.tmp_FECHA_COMPROMISO_CRM c
    INNER JOIN dbo.kpi_crm_cartera k ON k.crm_cartera = c.cartera
    WHERE c.FechaGestion >= @inicio AND c.FechaGestion < @fin
      AND TRY_CAST(c.RutCliente AS bigint) IS NOT NULL
    GROUP BY c.cartera, TRY_CAST(c.RutCliente AS bigint), c.FechaGestion, c.FechaCompromiso;
    INSERT INTO @stats VALUES ('compromisos', @@ROWCOUNT);

    COMMIT TRANSACTION;

    -- Resultado 1: filas cargadas por paso.
    SELECT @periodo AS periodo, paso, filas FROM @stats;

    -- Resultado 2: valores de ContactoGestion sin catalogo (cuentan como SIN CONTACTO); agregarlos a kpi_tipo_contacto.
    SELECT ISNULL(NULLIF(UPPER(LTRIM(RTRIM(g.ContactoGestion))), ''), '(VACIO)') AS valor_sin_catalogo, COUNT_BIG(1) AS gestiones
    FROM dbo.tmp_GEST_CRM g
    INNER JOIN dbo.kpi_crm_cartera k ON k.crm_cartera = g.cartera
    LEFT JOIN dbo.kpi_tipo_contacto t
        ON t.valor = ISNULL(NULLIF(UPPER(LTRIM(RTRIM(g.ContactoGestion))), ''), '(VACIO)')
    WHERE g.GestionFecha >= @inicio AND g.GestionFecha < @fin AND t.valor IS NULL
    GROUP BY ISNULL(NULLIF(UPPER(LTRIM(RTRIM(g.ContactoGestion))), ''), '(VACIO)')
    ORDER BY gestiones DESC;
END;
GO

/* ------------------------------------------------------------
   Punto de entrada: un periodo, o por defecto el mes actual y los 3 anteriores
   (los que compara el dashboard).
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.sp_kpi_operacional_cargar', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_kpi_operacional_cargar;
GO

CREATE PROCEDURE dbo.sp_kpi_operacional_cargar
    @periodo CHAR(7) = NULL   -- 'YYYY-MM'; NULL = mes actual y 3 anteriores
AS
BEGIN
    SET NOCOUNT ON;

    IF @periodo IS NOT NULL
    BEGIN
        EXEC dbo.sp_kpi_operacional_cargar_periodo @periodo = @periodo;
        RETURN;
    END;

    DECLARE @mes_actual DATE = DATEADD(DAY, 1 - DAY(GETDATE()), CAST(GETDATE() AS date));
    DECLARE @i INT = 3, @p CHAR(7);
    WHILE @i >= 0
    BEGIN
        SET @p = CONVERT(char(7), DATEADD(MONTH, -@i, @mes_actual), 126);
        EXEC dbo.sp_kpi_operacional_cargar_periodo @periodo = @p;
        SET @i = @i - 1;
    END;
END;
GO
