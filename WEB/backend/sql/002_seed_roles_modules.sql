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
GO
