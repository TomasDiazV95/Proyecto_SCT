IF OBJECT_ID('dbo.roles', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.roles (
        id INT IDENTITY(1,1) PRIMARY KEY,
        code VARCHAR(30) NOT NULL UNIQUE,
        name VARCHAR(60) NOT NULL,
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID('dbo.modules', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.modules (
        id INT IDENTITY(1,1) PRIMARY KEY,
        code VARCHAR(60) NOT NULL UNIQUE,
        display_name VARCHAR(120) NOT NULL,
        route_path VARCHAR(120) NOT NULL,
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID('dbo.users', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.users (
        id INT IDENTITY(1,1) PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        full_name VARCHAR(150) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role_id INT NOT NULL,
        is_active BIT NOT NULL DEFAULT 1,
        must_change_password BIT NOT NULL DEFAULT 1,
        failed_login_attempts INT NOT NULL DEFAULT 0,
        locked_until DATETIME2 NULL,
        last_login_at DATETIME2 NULL,
        created_by_user_id INT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_users_role FOREIGN KEY (role_id) REFERENCES dbo.roles(id),
        CONSTRAINT FK_users_created_by FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(id)
    );
END;
GO

IF OBJECT_ID('dbo.user_modules', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_modules (
        user_id INT NOT NULL,
        module_id INT NOT NULL,
        created_by_user_id INT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_user_modules PRIMARY KEY (user_id, module_id),
        CONSTRAINT FK_user_modules_user FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT FK_user_modules_module FOREIGN KEY (module_id) REFERENCES dbo.modules(id),
        CONSTRAINT FK_user_modules_created_by FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(id)
    );
END;
GO

IF OBJECT_ID('dbo.password_reset_tokens', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.password_reset_tokens (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL,
        token_hash VARCHAR(255) NOT NULL,
        expires_at DATETIME2 NOT NULL,
        used_at DATETIME2 NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_prt_user FOREIGN KEY (user_id) REFERENCES dbo.users(id)
    );
END;
GO

IF OBJECT_ID('dbo.audit_logs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.audit_logs (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        actor_user_id INT NULL,
        action VARCHAR(80) NOT NULL,
        target_type VARCHAR(40) NULL,
        target_id INT NULL,
        detail NVARCHAR(MAX) NULL,
        ip_address VARCHAR(64) NULL,
        user_agent VARCHAR(500) NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_audit_actor FOREIGN KEY (actor_user_id) REFERENCES dbo.users(id)
    );
END;
GO
