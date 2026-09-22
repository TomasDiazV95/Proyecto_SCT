/*
   Indices no destructivos para el dashboard Contactabilidad Itaú Vencida.
   Ejecutar en una ventana de mantenimiento y revisar los planes de ejecucion
   antes de promover a produccion.
*/

IF OBJECT_ID('dbo.contencion_itau_vencida', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.contencion_itau_vencida', 'fecha_carga') IS NOT NULL
   AND COL_LENGTH('dbo.contencion_itau_vencida', 'GESTOR') IS NOT NULL
   AND COL_LENGTH('dbo.contencion_itau_vencida', 'OPER') IS NOT NULL
   AND COL_LENGTH('dbo.contencion_itau_vencida', 'RUT') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE object_id = OBJECT_ID('dbo.contencion_itau_vencida')
         AND name = 'IX_contencion_itau_fecha_gestor_oper_rut'
   )
BEGIN
    CREATE INDEX IX_contencion_itau_fecha_gestor_oper_rut
        ON dbo.contencion_itau_vencida(fecha_carga, GESTOR, OPER, RUT);
END;
GO

IF OBJECT_ID('dbo.asignacion_itau_vencida', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.asignacion_itau_vencida', 'fecha_carga') IS NOT NULL
   AND COL_LENGTH('dbo.asignacion_itau_vencida', 'Numero_Cuenta') IS NOT NULL
   AND COL_LENGTH('dbo.asignacion_itau_vencida', 'Rut') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE object_id = OBJECT_ID('dbo.asignacion_itau_vencida')
         AND name = 'IX_asignacion_itau_fecha_numero_cuenta_rut'
   )
BEGIN
    CREATE INDEX IX_asignacion_itau_fecha_numero_cuenta_rut
        ON dbo.asignacion_itau_vencida(fecha_carga, Numero_Cuenta, Rut);
END;
GO

IF OBJECT_ID('dbo.tmp_GEST_CRM', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.tmp_GEST_CRM', 'cartera') IS NOT NULL
   AND COL_LENGTH('dbo.tmp_GEST_CRM', 'GestionFecha') IS NOT NULL
   AND COL_LENGTH('dbo.tmp_GEST_CRM', 'rut') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE object_id = OBJECT_ID('dbo.tmp_GEST_CRM')
         AND name = 'IX_tmp_GEST_CRM_cartera_fecha_rut'
   )
BEGIN
    CREATE INDEX IX_tmp_GEST_CRM_cartera_fecha_rut
        ON dbo.tmp_GEST_CRM(cartera, GestionFecha, rut);
END;
GO
