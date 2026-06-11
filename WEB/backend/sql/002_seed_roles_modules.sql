IF NOT EXISTS (SELECT 1 FROM dbo.roles WHERE code = 'super_admin')
    INSERT INTO dbo.roles(code, name) VALUES ('super_admin', 'Super Admin');

IF NOT EXISTS (SELECT 1 FROM dbo.roles WHERE code = 'admin')
    INSERT INTO dbo.roles(code, name) VALUES ('admin', 'Admin');

IF NOT EXISTS (SELECT 1 FROM dbo.roles WHERE code = 'coordinador')
    INSERT INTO dbo.roles(code, name) VALUES ('coordinador', 'Coordinador');

IF NOT EXISTS (SELECT 1 FROM dbo.roles WHERE code = 'supervisor')
    INSERT INTO dbo.roles(code, name) VALUES ('supervisor', 'Supervisor');

IF NOT EXISTS (SELECT 1 FROM dbo.roles WHERE code = 'ejecutivo')
    INSERT INTO dbo.roles(code, name) VALUES ('ejecutivo', 'Ejecutivo');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'sc-tardia')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('sc-tardia', 'SC Tardia', '/sc-tardia');

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'sc-temprana')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('sc-temprana', 'SC Temprana', '/sc-temprana');

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'gm')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('gm', 'GM', '/gm');

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'la-araucana')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('la-araucana', 'La Araucana', '/la-araucana');

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'porsche')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('porsche', 'Porsche', '/porsche');

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'sth')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('sth', 'STH', '/sth');

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'bit')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('bit', 'BIT', '/bit');

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'itau-castigo')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('itau-castigo', 'Itaú Castigo', '/itau-castigo');
ELSE
    UPDATE dbo.modules SET display_name = 'Itaú Castigo', route_path = '/itau-castigo', is_active = 1 WHERE code = 'itau-castigo';

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'global')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('global', 'Acceso Global', '/');
ELSE
    UPDATE dbo.modules SET display_name = 'Acceso Global', route_path = '/', is_active = 1 WHERE code = 'global';

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'productividad')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('productividad', 'Panel de Productividad', '/productividad');
ELSE
    UPDATE dbo.modules SET display_name = 'Panel de Productividad', route_path = '/productividad', is_active = 1 WHERE code = 'productividad';

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'contactabilidad')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('contactabilidad', 'Panel de Contactabilidad', '/contactabilidad');
ELSE
    UPDATE dbo.modules SET display_name = 'Panel de Contactabilidad', route_path = '/contactabilidad', is_active = 1 WHERE code = 'contactabilidad';

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'factura')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('factura', 'Panel de Factura', '/factura');
ELSE
    UPDATE dbo.modules SET display_name = 'Panel de Factura', route_path = '/factura', is_active = 1 WHERE code = 'factura';

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'administrativas')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('administrativas', 'Panel de Administrativas', '/administrativas');
ELSE
    UPDATE dbo.modules SET display_name = 'Panel de Administrativas', route_path = '/administrativas', is_active = 1 WHERE code = 'administrativas';

IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'admin')
    INSERT INTO dbo.modules(code, display_name, route_path) VALUES ('admin', 'Panel Admin', '/admin');
ELSE
    UPDATE dbo.modules SET display_name = 'Panel Admin', route_path = '/admin', is_active = 1 WHERE code = 'admin';

UPDATE dbo.modules
SET is_active = 0
WHERE code IN (
    'facturas',
    'factura-reportes',
    'administrativas-formulario',
    'admin-usuarios',
    'admin-permisos',
    'admin-configuracion'
);
GO
