/* ============================================================
   KPI Operacional: tablas consolidadas + carga por stored procedure.

   Piloto: Itau Vencida, Itau Castigo y Banco Internacional (BIT).
   Reglas de negocio (definidas por la usuaria):
     - Caso = RUT unico; las operaciones son dato secundario.
     - Asignacion del periodo = la ultima del mes.
     - Saldo asignado: Itau Vencida Monto_Asignado, Itau Castigo SDO_CAST_ACTUAL, BIT DEUDA_TOTAL.
     - Pagos: en carteras medidas por contencion es la contencion (Itau Vencida SALDO_CONT,
       BIT Vigente mto_contiene); en castigos es el recupero.
     - Carteras: Itau Vencida y Castigo; BIT solo Vigente (30-90 / 90+) y Castigo.
     - Tramos propios de cada cartera, como en productividad.
     - Gestiones: solo dbo.tmp_GEST_CRM.

   Uso:
     EXEC dbo.sp_kpi_operacional_cargar;                      -- mes anterior y actual
     EXEC dbo.sp_kpi_operacional_cargar @periodo = '2026-09';  -- un periodo

   Nota: la base esta en nivel de compatibilidad 100: no usar TRY_CONVERT (TRY_CAST si).
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
        saldo_asignado DECIMAL(38,2) NULL,
        fecha_corte DATE NULL,
        source_file NVARCHAR(260) NULL
    );
    CREATE INDEX IX_kpi_asignacion_periodo ON dbo.kpi_asignacion(periodo, mandante, cartera) INCLUDE (rut, tramo, producto, saldo_asignado);
    CREATE INDEX IX_kpi_asignacion_rut ON dbo.kpi_asignacion(periodo, mandante, rut);
END;
GO

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
    (532, N'BANCO INTERNACIONAL', NULL, N'BANCO INTERNACIONAL')
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

    DECLARE @stats TABLE (paso NVARCHAR(40), filas INT);

    -- Ultimo archivo de contencion Itau Vencida del mes (base del tramo y de los pagos).
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

    BEGIN TRANSACTION;

    DELETE FROM dbo.kpi_asignacion WHERE periodo = @periodo;
    DELETE FROM dbo.kpi_pagos WHERE periodo = @periodo;
    DELETE FROM dbo.kpi_gestiones_rut WHERE periodo = @periodo;
    DELETE FROM dbo.kpi_compromisos WHERE periodo = @periodo;

    /* ---------------- Asignacion ---------------- */

    -- Itau Vencida: tramo = fase de la contencion Phoenix del mes (como en productividad Itau Vencida);
    -- sin fase, el estado de la asignacion (Moroso / Vencido / Castigado).
    ;WITH cont AS (
        SELECT OPER, MAX(CAST(FASE_PROY_MAX AS int)) AS fase
        FROM dbo.contencion_itau_vencida
        WHERE source_file = @contencion_itv AND fecha_carga = @contencion_itv_fecha AND GESTOR = 'PHOENIX'
        GROUP BY OPER
    )
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'ITAÚ', N'VENCIDA', CAST(a.Rut AS bigint), a.Numero_Cuenta, NULLIF(LTRIM(RTRIM(a.Producto)), ''),
           CASE WHEN c.fase IS NOT NULL THEN CONCAT('Fase ', c.fase)
                ELSE CONCAT('Sin fase - ', ISNULL(NULLIF(LTRIM(RTRIM(a.Estado)), ''), 'Sin estado')) END,
           a.Monto_Asignado, @asig_itv_fecha, a.source_file
    FROM dbo.asignacion_itau_vencida a
    LEFT JOIN cont c ON c.OPER = a.Numero_Cuenta
    WHERE a.source_file = @asig_itv AND a.Rut IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_itau_vencida', @@ROWCOUNT);

    -- Itau Castigo: un periodo por archivo (el ETL deja solo la ultima del mes).
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'ITAÚ', N'CASTIGO', CAST(a.RUT AS bigint), NULL, NULL, 'Castigo',
           a.SDO_CAST_ACTUAL, a.fecha_carga, a.source_file
    FROM dbo.tmp_itau_castigo_asignacion a
    WHERE a.PERIODO = @periodo_yyyymm AND a.RUT IS NOT NULL;
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
                   ELSE ISNULL(NULLIF(UPPER(LTRIM(RTRIM(a.CAMPANA))), ''), N'SIN CAMPAÑA')
               END AS cartera_kpi
        FROM dbo.tmp_BIT_asignacion a
        WHERE a.periodo = @periodo
    )
    INSERT INTO dbo.kpi_asignacion (periodo, mandante, cartera, rut, operacion, producto, tramo, saldo_asignado, fecha_corte, source_file)
    SELECT @periodo, N'BANCO INTERNACIONAL', b.cartera_kpi, TRY_CAST(b.RUT AS bigint), b.NRO_OPERACION,
           CASE WHEN UPPER(b.GRUPO_PRODUCTO) IN ('TARJETA', 'TARJETAS') THEN 'Tarjetas' ELSE NULLIF(LTRIM(RTRIM(b.GRUPO_PRODUCTO)), '') END,
           CASE
               WHEN b.cartera_kpi = 'CASTIGO' THEN 'Castigo'
               WHEN b.cartera_kpi <> 'VIGENTE' THEN 'Sin tramo'
               WHEN c.t IN ('T1', 'T2', 'T3') THEN '30-90'
               WHEN c.t IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
               -- Sin tramo en la contencion: segun la campana.
               WHEN UPPER(b.CAMPANA) LIKE '%VENCIDA%' THEN '90+'
               ELSE '30-90'
           END,
           b.DEUDA_TOTAL, TRY_CAST(b.fecha_carga AS date), b.source_file
    FROM base b
    LEFT JOIN cont c ON c.op = TRY_CAST(b.NRO_OPERACION AS bigint)
    WHERE TRY_CAST(b.RUT AS bigint) IS NOT NULL;
    INSERT INTO @stats VALUES ('asig_bit', @@ROWCOUNT);

    /* ---------------- Pagos ---------------- */

    -- Itau Vencida: contencion (SALDO_CONT) del ultimo archivo del mes, solo GESTOR PHOENIX.
    INSERT INTO dbo.kpi_pagos (periodo, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, fecha_corte, source_file)
    SELECT @periodo, N'ITAÚ', N'VENCIDA', CAST(c.RUT AS bigint), c.OPER, c.SALDO_CONT, 'CONTENCION',
           CASE WHEN ISNULL(c.EFECT_RECUPERADO, 0) > 0 THEN 1 ELSE 0 END, NULL, c.fecha_carga, c.source_file
    FROM dbo.contencion_itau_vencida c
    WHERE c.source_file = @contencion_itv AND c.fecha_carga = @contencion_itv_fecha
      AND c.GESTOR = 'PHOENIX'
      AND c.RUT IS NOT NULL
      AND (ISNULL(c.SALDO_CONT, 0) > 0 OR ISNULL(c.EFECT_RECUPERADO, 0) > 0);
    INSERT INTO @stats VALUES ('pagos_itau_vencida', @@ROWCOUNT);

    -- Itau Castigo: recupero del ultimo archivo del mes.
    INSERT INTO dbo.kpi_pagos (periodo, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, fecha_corte, source_file)
    SELECT @periodo, N'ITAÚ', N'CASTIGO', CAST(r.RUT AS bigint), NULL, r.RECUPERO, 'RECUPERO', 1,
           TRY_CAST(r.FECHA_RECUPERO AS date), r.fecha_carga, r.source_file
    FROM dbo.recup_itau_castigo r
    WHERE r.source_file = @recup_itc AND r.fecha_carga = @recup_itc_fecha
      AND r.RUT IS NOT NULL AND ISNULL(r.RECUPERO, 0) > 0;
    INSERT INTO @stats VALUES ('pagos_itau_castigo', @@ROWCOUNT);

    -- BIT Vigente: contencion (mto_contiene). La cartera se toma de la asignacion por operacion o RUT;
    -- si no esta asignada, Vigente (el archivo de contencion es el de la cartera vigente).
    ;WITH asig_op AS (
        SELECT TRY_CAST(operacion AS bigint) AS op, MAX(cartera) AS cartera
        FROM dbo.kpi_asignacion
        WHERE periodo = @periodo AND mandante = N'BANCO INTERNACIONAL' AND cartera <> 'CASTIGO'
        GROUP BY TRY_CAST(operacion AS bigint)
    ),
    asig_rut AS (
        SELECT rut, MAX(cartera) AS cartera
        FROM dbo.kpi_asignacion
        WHERE periodo = @periodo AND mandante = N'BANCO INTERNACIONAL' AND cartera <> 'CASTIGO'
        GROUP BY rut
    )
    INSERT INTO dbo.kpi_pagos (periodo, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, fecha_corte, source_file)
    SELECT @periodo, N'BANCO INTERNACIONAL', COALESCE(ao.cartera, ar.cartera, 'VIGENTE'),
           TRY_CAST(c.rut AS bigint), c.con_no, c.mto_contiene, 'CONTENCION',
           CASE WHEN c.contiene = 1 THEN 1 ELSE 0 END, NULL, c.fecha_carga, c.source_file
    FROM dbo.tmp_BIT_contencion c
    LEFT JOIN asig_op ao ON ao.op = TRY_CAST(c.con_no AS bigint)
    LEFT JOIN asig_rut ar ON ar.rut = TRY_CAST(c.rut AS bigint)
    WHERE c.periodo = @periodo AND TRY_CAST(c.rut AS bigint) IS NOT NULL AND ISNULL(c.mto_contiene, 0) > 0;
    INSERT INTO @stats VALUES ('pagos_bit_contencion', @@ROWCOUNT);

    -- BIT Castigo: recupero.
    INSERT INTO dbo.kpi_pagos (periodo, mandante, cartera, rut, operacion, monto, tipo_monto, pago_efectivo, fecha_pago, fecha_corte, source_file)
    SELECT @periodo, N'BANCO INTERNACIONAL', 'CASTIGO', TRY_CAST(b.RUT AS bigint), NULL, b.MTO_RECUPERO_FINAL, 'RECUPERO', 1,
           NULL, b.fecha_carga, b.source_file
    FROM dbo.tmp_BIT_castigo b
    WHERE b.periodo = @periodo AND TRY_CAST(b.RUT AS bigint) IS NOT NULL AND ISNULL(b.MTO_RECUPERO_FINAL, 0) > 0;
    INSERT INTO @stats VALUES ('pagos_bit_castigo', @@ROWCOUNT);

    -- Tramo y producto del pago: los de la asignacion por operacion y, si no, por RUT; si no, 'Sin asignación'.
    UPDATE p
    SET tramo = COALESCE(ao.tramo, ar.tramo, N'Sin asignación'),
        producto = COALESCE(ao.producto, ar.producto)
    FROM dbo.kpi_pagos p
    OUTER APPLY (
        SELECT TOP (1) a.tramo, a.producto
        FROM dbo.kpi_asignacion a
        WHERE a.periodo = p.periodo AND a.mandante = p.mandante AND a.cartera = p.cartera
          AND p.operacion IS NOT NULL AND a.operacion = p.operacion
    ) ao
    OUTER APPLY (
        SELECT TOP (1) a.tramo, a.producto
        FROM dbo.kpi_asignacion a
        WHERE a.periodo = p.periodo AND a.mandante = p.mandante AND a.cartera = p.cartera AND a.rut = p.rut
        ORDER BY a.saldo_asignado DESC
    ) ar
    WHERE p.periodo = @periodo;

    /* ---------------- Gestiones ---------------- */

    -- Un registro por periodo, cartera CRM y RUT, con el mejor contacto del mes: Directo > Indirecto > Sin contacto.
    -- Los valores EXCLUIR (envios masivos, etc.) no cuentan como gestion. Los no catalogados cuentan como Sin contacto.
    ;WITH g AS (
        SELECT g.cartera AS crm_cartera,
               TRY_CAST(g.rut AS bigint) AS rut,
               g.GestionFecha AS fecha,
               ISNULL(t.tipo, 'SIN CONTACTO') AS tipo
        FROM dbo.tmp_GEST_CRM g
        INNER JOIN dbo.kpi_crm_cartera k ON k.crm_cartera = g.cartera
        LEFT JOIN dbo.kpi_tipo_contacto t
            ON t.valor = ISNULL(NULLIF(UPPER(LTRIM(RTRIM(g.ContactoGestion))), ''), '(VACIO)')
        WHERE g.GestionFecha >= @inicio AND g.GestionFecha < @fin
          AND TRY_CAST(g.rut AS bigint) IS NOT NULL
    )
    INSERT INTO dbo.kpi_gestiones_rut (periodo, crm_cartera, rut, n_gestiones, tipo_contacto,
                                       fecha_primera_gestion, fecha_primer_directo, fecha_primer_indirecto)
    SELECT @periodo, crm_cartera, rut, COUNT(*),
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

    /* ---------------- Compromisos ---------------- */

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
   Punto de entrada: un periodo, o por defecto el mes anterior y el actual
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.sp_kpi_operacional_cargar', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_kpi_operacional_cargar;
GO

CREATE PROCEDURE dbo.sp_kpi_operacional_cargar
    @periodo CHAR(7) = NULL   -- 'YYYY-MM'; NULL = mes anterior y mes actual
AS
BEGIN
    SET NOCOUNT ON;

    IF @periodo IS NOT NULL
    BEGIN
        EXEC dbo.sp_kpi_operacional_cargar_periodo @periodo = @periodo;
        RETURN;
    END;

    DECLARE @mes_actual DATE = DATEADD(DAY, 1 - DAY(GETDATE()), CAST(GETDATE() AS date));
    DECLARE @anterior CHAR(7) = CONVERT(char(7), DATEADD(MONTH, -1, @mes_actual), 126);
    DECLARE @actual CHAR(7) = CONVERT(char(7), @mes_actual, 126);

    EXEC dbo.sp_kpi_operacional_cargar_periodo @periodo = @anterior;
    EXEC dbo.sp_kpi_operacional_cargar_periodo @periodo = @actual;
END;
GO
