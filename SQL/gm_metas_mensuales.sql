IF OBJECT_ID('dbo.gm_metas_mensuales', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.gm_metas_mensuales (
        periodo DATE NOT NULL,
        bucket VARCHAR(20) NOT NULL,
        meta_contencion_pct DECIMAL(10,2) NOT NULL,
        meta_normalizacion_pct DECIMAL(10,2) NOT NULL,
        ponderador_contencion_pct DECIMAL(10,2) NOT NULL,
        ponderador_normalizacion_pct DECIMAL(10,2) NOT NULL,
        activo BIT NOT NULL CONSTRAINT DF_gm_metas_mensuales_activo DEFAULT (1),
        CONSTRAINT PK_gm_metas_mensuales PRIMARY KEY (periodo, bucket)
    );
END;
GO

MERGE dbo.gm_metas_mensuales AS target
USING (
    SELECT CAST('2026-04-01' AS DATE) AS periodo, '6 a 30' AS bucket, 82.00 AS meta_contencion_pct, 30.00 AS meta_normalizacion_pct, 80.00 AS ponderador_contencion_pct, 20.00 AS ponderador_normalizacion_pct
    UNION ALL SELECT CAST('2026-04-01' AS DATE), '31 a 60', 77.00, 24.00, 80.00, 20.00
    UNION ALL SELECT CAST('2026-04-01' AS DATE), '61 a 90', 72.00, 22.00, 70.00, 30.00
    UNION ALL SELECT CAST('2026-04-01' AS DATE), '91 a 150', 71.00, 20.00, 70.00, 30.00
    UNION ALL SELECT CAST('2026-09-01' AS DATE), '6 a 30', 82.00, 26.00, 80.00, 20.00
    UNION ALL SELECT CAST('2026-09-01' AS DATE), '31 a 60', 73.00, 24.00, 80.00, 20.00
    UNION ALL SELECT CAST('2026-09-01' AS DATE), '61 a 90', 72.00, 23.00, 70.00, 30.00
    UNION ALL SELECT CAST('2026-09-01' AS DATE), '91 a 150', 72.00, 21.00, 70.00, 30.00
) AS source
ON target.periodo = source.periodo
AND target.bucket = source.bucket
WHEN MATCHED THEN
    UPDATE SET
        target.meta_contencion_pct = source.meta_contencion_pct,
        target.meta_normalizacion_pct = source.meta_normalizacion_pct,
        target.ponderador_contencion_pct = source.ponderador_contencion_pct,
        target.ponderador_normalizacion_pct = source.ponderador_normalizacion_pct,
        target.activo = 1
WHEN NOT MATCHED THEN
    INSERT (
        periodo,
        bucket,
        meta_contencion_pct,
        meta_normalizacion_pct,
        ponderador_contencion_pct,
        ponderador_normalizacion_pct,
        activo
    )
    VALUES (
        source.periodo,
        source.bucket,
        source.meta_contencion_pct,
        source.meta_normalizacion_pct,
        source.ponderador_contencion_pct,
        source.ponderador_normalizacion_pct,
        1
    );
GO

-- Ponderador 2: peso del tramo en el cumplimiento individual de la ejecutiva (pestaña General).
-- Los tramos tempranos llevan el mismo peso y, sumado al del 91 a 150, da 100.
-- NULL = el mes no tiene pesos y el cumplimiento individual pondera por deuda.
IF COL_LENGTH('dbo.gm_metas_mensuales', 'ponderador_tramo_pct') IS NULL
    ALTER TABLE dbo.gm_metas_mensuales ADD ponderador_tramo_pct DECIMAL(10,2) NULL;
GO

UPDATE dbo.gm_metas_mensuales
SET ponderador_tramo_pct = CASE WHEN bucket = '91 a 150' THEN 30.00 ELSE 70.00 END
WHERE periodo IN ('2026-09-01', '2026-10-01');
GO

-- Pesos de otro mes (ejemplo):
-- UPDATE dbo.gm_metas_mensuales
-- SET ponderador_tramo_pct = CASE WHEN bucket = '91 a 150' THEN 40.00 ELSE 60.00 END
-- WHERE periodo = '2026-10-01';

-- Para crear un nuevo mes, copiar mes anterior y editar solo metas/ponderadores.
-- Ejemplo:
-- INSERT INTO dbo.gm_metas_mensuales (periodo, bucket, meta_contencion_pct, meta_normalizacion_pct, ponderador_contencion_pct, ponderador_normalizacion_pct, activo)
-- SELECT '2026-05-01', bucket, meta_contencion_pct, meta_normalizacion_pct, ponderador_contencion_pct, ponderador_normalizacion_pct, 1
-- FROM dbo.gm_metas_mensuales
-- WHERE periodo = '2026-04-01';
