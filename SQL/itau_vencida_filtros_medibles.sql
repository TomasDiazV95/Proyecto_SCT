-- Casos medibles de Itau Vencida por mes (productividad).
-- Solo es medible lo que esta configurado aqui; todo lo demas queda como no medible.
-- Se administra desde Panel Administrativo > Itau > "Casos medibles Itau Vencida".
--
-- Reglas:
--   * columna: DETALLE_MARCA, CANAL, PRODUCTO o SEGMENTO (columnas de contencion_itau_vencida).
--   * En cada columna configurada, el caso debe tener uno de sus valores.
--   * Columnas distintas se combinan con AND. Una columna sin valores no restringe.
--   * Un mes sin nada configurado no tiene casos medibles. No se hereda del mes anterior.
--   * Se compara sin mayusculas ni espacios sobrantes, con el valor exacto (no "contiene").
--   * periodo en formato 'YYYY-MM' (ej. '2026-09').
IF OBJECT_ID('dbo.itau_vencida_filtros_medibles', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.itau_vencida_filtros_medibles (
        periodo CHAR(7) NOT NULL,
        columna VARCHAR(30) NOT NULL,
        valor NVARCHAR(200) NOT NULL,
        activo BIT NOT NULL CONSTRAINT DF_itau_vencida_filtros_medibles_activo DEFAULT (1),
        CONSTRAINT PK_itau_vencida_filtros_medibles PRIMARY KEY (periodo, columna, valor),
        CONSTRAINT CK_itau_vencida_filtros_medibles_columna CHECK (columna IN ('DETALLE_MARCA', 'CANAL', 'PRODUCTO', 'SEGMENTO')),
        CONSTRAINT CK_itau_vencida_filtros_medibles_periodo CHECK (periodo LIKE '[2][0-9][0-9][0-9]-[01][0-9]')
    );
END;
GO

-- Septiembre 2026: medible = CANAL 'TERRENO PREJUDICIAL' y SEGMENTO 'ITAÚ SUCURSALES' o 'CORNER'.
MERGE dbo.itau_vencida_filtros_medibles AS target
USING (
    SELECT '2026-09' AS periodo, 'CANAL' AS columna, N'TERRENO PREJUDICIAL' AS valor
    UNION ALL SELECT '2026-09', 'SEGMENTO', N'ITAÚ SUCURSALES'
    UNION ALL SELECT '2026-09', 'SEGMENTO', N'CORNER'
) AS source
ON target.periodo = source.periodo
AND target.columna = source.columna
AND target.valor = source.valor
WHEN MATCHED THEN
    UPDATE SET target.activo = 1
WHEN NOT MATCHED THEN
    INSERT (periodo, columna, valor, activo)
    VALUES (source.periodo, source.columna, source.valor, 1);
GO
