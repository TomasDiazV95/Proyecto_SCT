MERGE dbo.sth_metas_mensuales AS target
USING (
    SELECT CAST('2026-05-01' AS DATE) AS periodo, 'Contención Hipotecario' AS producto, 'Ciclo 1' AS tramo, 80.00 AS meta_contenido_pct, 100.00 AS ponderador_nivel_1_pct
    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Contención Hipotecario', 'Ciclo 2', 78.00, 100.00
    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Contención Hipotecario', 'Ciclo 3', 76.00, 100.00

    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Contención Consumo', 'Ciclo 1', 55.00, 50.00
    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Contención Consumo', 'Ciclo 2', 36.00, 50.00

    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Pyme', 'Ciclo 1', 69.00, 60.00
    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Pyme', 'Ciclo 2', 49.00, 24.00
    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Pyme', 'Ciclo 3', 47.00, 16.00

    UNION ALL SELECT CAST('2026-05-01' AS DATE), 'Tarjeta', 'Multiciclo', 32.00, 100.00
) AS source
ON  target.periodo = source.periodo
AND target.producto = source.producto
AND target.tramo = source.tramo

WHEN MATCHED THEN
    UPDATE SET
        target.meta_contenido_pct = source.meta_contenido_pct,
        target.ponderador_nivel_1_pct = source.ponderador_nivel_1_pct,
        target.activo = 1

WHEN NOT MATCHED THEN
    INSERT (
        periodo,
        producto,
        tramo,
        meta_contenido_pct,
        ponderador_nivel_1_pct,
        activo
    )
    VALUES (
        source.periodo,
        source.producto,
        source.tramo,
        source.meta_contenido_pct,
        source.ponderador_nivel_1_pct,
        1
    );
GO