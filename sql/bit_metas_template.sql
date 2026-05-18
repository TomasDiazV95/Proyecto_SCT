/*
Plantilla mensual para cargar metas BIT manualmente.
Regla operativa: en METAS usar solo INSERT o MERGE (sin DELETE).
Reemplaza @periodo y los valores de meta segun corresponda.
*/

DECLARE @periodo CHAR(7) = '2026-05';

/* Opcion 1: INSERT puro (sirve si el periodo+tramo no existe aun) */
-- INSERT INTO dbo.tmp_BIT_metas (periodo, tramo, meta)
-- VALUES
-- (@periodo, '30-89', 0.710000),
-- (@periodo, '90+',   0.150000);

/* Opcion 2: MERGE (recomendada, inserta o actualiza por periodo+tramo) */
MERGE dbo.tmp_BIT_metas AS target
USING (
    SELECT @periodo AS periodo, '30-89' AS tramo, CAST(0.710000 AS DECIMAL(10,6)) AS meta
    UNION ALL
    SELECT @periodo, '90+', CAST(0.150000 AS DECIMAL(10,6))
) AS src
ON target.periodo = src.periodo AND target.tramo = src.tramo
WHEN MATCHED THEN
    UPDATE SET target.meta = src.meta
WHEN NOT MATCHED BY TARGET THEN
    INSERT (periodo, tramo, meta)
    VALUES (src.periodo, src.tramo, src.meta);

SELECT periodo, tramo, meta
FROM dbo.tmp_BIT_metas
WHERE periodo = @periodo
ORDER BY CASE tramo WHEN '30-89' THEN 1 WHEN '90+' THEN 2 ELSE 99 END, tramo;
