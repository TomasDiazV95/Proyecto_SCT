-- Metas de contencion Itau Vencida (productividad por ejecutivo).
-- Se toma la ultima vigencia con periodo <= mes consultado.
-- meta_contencion y ponderacion son fracciones: 0.3500 = 35%.
-- producto: CONSUMO (GLOSA_TIPO_CARTERA = 'Consumo') o HIPOTECARIO (GLOSA_TIPO_CARTERA = 'Vivienda').
-- fase: FASE_PROY_MAX de la contencion. Fases sin meta no entran al calculo.
IF OBJECT_ID('dbo.itau_vencida_metas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.itau_vencida_metas (
        periodo DATE NOT NULL,
        producto VARCHAR(20) NOT NULL,
        fase INT NOT NULL,
        meta_contencion DECIMAL(9,4) NOT NULL,
        ponderacion DECIMAL(9,4) NOT NULL,
        activo BIT NOT NULL CONSTRAINT DF_itau_vencida_metas_activo DEFAULT (1),
        CONSTRAINT PK_itau_vencida_metas PRIMARY KEY (periodo, producto, fase)
    );
END;
GO

MERGE dbo.itau_vencida_metas AS target
USING (
    SELECT CAST('2026-09-01' AS DATE) AS periodo, 'CONSUMO' AS producto, 4 AS fase, 0.35 AS meta_contencion, 0.60 AS ponderacion
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'CONSUMO', 5, 0.25, 0.60
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'CONSUMO', 6, 0.13, 0.60
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'CONSUMO', 7, 0.10, 0.60
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'HIPOTECARIO', 4, 0.75, 0.40
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'HIPOTECARIO', 5, 0.64, 0.40
    UNION ALL SELECT CAST('2026-09-01' AS DATE), 'HIPOTECARIO', 6, 0.55, 0.40
) AS source
ON target.periodo = source.periodo
AND target.producto = source.producto
AND target.fase = source.fase
WHEN MATCHED THEN
    UPDATE SET
        target.meta_contencion = source.meta_contencion,
        target.ponderacion = source.ponderacion,
        target.activo = 1
WHEN NOT MATCHED THEN
    INSERT (periodo, producto, fase, meta_contencion, ponderacion, activo)
    VALUES (source.periodo, source.producto, source.fase, source.meta_contencion, source.ponderacion, 1);
GO
