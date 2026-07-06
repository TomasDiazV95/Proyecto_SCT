IF EXISTS (SELECT 1 FROM dbo.modules WHERE code = 'factura')
BEGIN
    UPDATE dbo.modules
    SET is_active = 0
    WHERE code = 'factura';
END;
