/*
  Modulos por panel y limpieza de permisos.

  - dbo.modules.parent_code: panel al que pertenece cada modulo. Asignar el panel
    ('productividad', 'kpi') abre todos sus modulos (auth/permissions.py).
  - Una sola vez: pasa los permisos de codigos sin uso al codigo correcto, quita las
    asignaciones antiguas de panel (no daban acceso real) y borra los modulos sobrantes.
  - Crea 'rrhh' y deja nombres y rutas al dia.

  Se puede ejecutar mas de una vez.
*/
IF COL_LENGTH('dbo.modules', 'parent_code') IS NULL
    ALTER TABLE dbo.modules ADD parent_code VARCHAR(50) NULL;
GO

SET XACT_ABORT ON;
BEGIN TRAN;

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'rrhh')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('rrhh', 'Panel RRHH', '/rrhh');

-- Solo la primera vez: despues de esta migracion, asignar un panel es una decision deliberada.
IF NOT EXISTS (SELECT 1 FROM dbo.audit_logs WHERE action = 'MIGRATION_008_MODULOS')
BEGIN
    -- 'kpi-avance-phoenix' y 'contactabilidad-itau-vencida' no los pide ninguna pantalla:
    -- sus usuarios pasan al codigo que si se usa.
    INSERT INTO dbo.user_modules(user_id, module_id, created_by_user_id)
    SELECT um.user_id, nuevo.id, um.created_by_user_id
    FROM dbo.user_modules um
    INNER JOIN dbo.modules viejo ON viejo.id = um.module_id
    INNER JOIN dbo.modules nuevo
        ON nuevo.code = CASE viejo.code
                            WHEN 'kpi-avance-phoenix' THEN 'kpi-diario'
                            WHEN 'contactabilidad-itau-vencida' THEN 'contactabilidad'
                        END
    WHERE viejo.code IN ('kpi-avance-phoenix', 'contactabilidad-itau-vencida')
      AND NOT EXISTS (SELECT 1 FROM dbo.user_modules x WHERE x.user_id = um.user_id AND x.module_id = nuevo.id);

    -- Los paneles asignados hasta hoy no abrian ningun modulo; se quitan para que nadie
    -- gane acceso al resto del panel. Cada usuario conserva sus modulos individuales.
    DELETE um
    FROM dbo.user_modules um
    INNER JOIN dbo.modules m ON m.id = um.module_id
    WHERE m.code IN (
        'productividad', 'kpi',
        'kpi-avance-phoenix', 'contactabilidad-itau-vencida',
        'facturas', 'factura-reportes', 'administrativas-formulario',
        'admin-usuarios', 'admin-permisos', 'admin-configuracion'
    );

    DELETE FROM dbo.modules
    WHERE code IN (
        'kpi-avance-phoenix', 'contactabilidad-itau-vencida',
        'facturas', 'factura-reportes', 'administrativas-formulario',
        'admin-usuarios', 'admin-permisos', 'admin-configuracion'
    );

    INSERT INTO dbo.audit_logs(actor_user_id, action, target_type, target_id, detail)
    VALUES (NULL, 'MIGRATION_008_MODULOS', 'module', NULL, 'Permisos migrados a modulos por panel');
END;

UPDATE m
SET display_name = v.display_name,
    route_path = v.route_path,
    parent_code = v.parent_code
FROM dbo.modules m
INNER JOIN (VALUES
    ('productividad',         'Panel de Productividad',         '/productividad',                           NULL),
    ('sc-tardia',             'SC Tardía',                      '/productividad/sc-tardia',                 'productividad'),
    ('sc-temprana',           'SC Temprana',                    '/productividad/sc-temprana',               'productividad'),
    ('gm',                    'General Motors',                 '/productividad/gm',                        'productividad'),
    ('itau-castigo',          'Itaú Castigo',                   '/productividad/itau-castigo',              'productividad'),
    ('itau-vencida',          'Itaú Vencida',                   '/productividad/itau-vencida',              'productividad'),
    ('itau-vigente',          'Itaú Vigente',                   '/productividad/itau-vigente',              'productividad'),
    ('sth',                   'Santander Hipotecario',          '/productividad/sth',                       'productividad'),
    ('bit',                   'Banco Internacional Vigente',    '/productividad/bit',                       'productividad'),
    ('bit-castigo',           'Banco Internacional Castigo',    '/productividad/bit-castigo',               'productividad'),
    ('la-araucana',           'Caja La Araucana',               '/productividad/la-araucana',               'productividad'),
    ('kpi',                   'Panel KPI',                      '/kpi',                                     NULL),
    ('bench',                 'BENCH KPI',                      '/kpi/bench',                               'kpi'),
    ('kpi-diario',            'KPI Avance Phoenix',             '/kpi/avance-phoenix',                      'kpi'),
    ('kpi-operacional',       'KPI Operacional',                '/kpi/operacional',                         'kpi'),
    ('contactabilidad',       'Panel de Contactabilidad',       '/contactabilidad',                         NULL),
    ('administrativas',       'Panel Administrativo',           '/administrativas',                         NULL),
    ('gestiones-diarias-sct', 'Gestiones Diarias SCT',          '/administrativas/gestiones-diarias-sct',   NULL),
    ('estrategia-asignacion', 'Panel Estrategia de Asignación', '/estrategia-asignacion',                   NULL),
    ('rrhh',                  'Panel RRHH',                     '/rrhh',                                    NULL),
    ('factura',               'Panel de Factura',               '/factura',                                 NULL),
    ('admin',                 'Panel Admin',                    '/admin',                                   NULL),
    ('global',                'Acceso Global',                  '/',                                        NULL)
) AS v(code, display_name, route_path, parent_code) ON v.code = m.code;

COMMIT;
GO
