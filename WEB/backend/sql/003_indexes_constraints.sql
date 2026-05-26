IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_users_role_active' AND object_id = OBJECT_ID('dbo.users'))
    CREATE INDEX IX_users_role_active ON dbo.users(role_id, is_active);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_user_modules_module' AND object_id = OBJECT_ID('dbo.user_modules'))
    CREATE INDEX IX_user_modules_module ON dbo.user_modules(module_id);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_prt_user_expires_used' AND object_id = OBJECT_ID('dbo.password_reset_tokens'))
    CREATE INDEX IX_prt_user_expires_used ON dbo.password_reset_tokens(user_id, expires_at, used_at);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_audit_actor_created' AND object_id = OBJECT_ID('dbo.audit_logs'))
    CREATE INDEX IX_audit_actor_created ON dbo.audit_logs(actor_user_id, created_at DESC);
GO
