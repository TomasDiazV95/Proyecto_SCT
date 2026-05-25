from database import get_connection, run_query


def get_user_by_email(email: str) -> dict | None:
    sql = """
    SELECT u.id, u.email, u.full_name, u.password_hash, u.is_active, u.must_change_password,
           u.failed_login_attempts, u.locked_until, r.code AS role_code
    FROM dbo.users u
    INNER JOIN dbo.roles r ON r.id = u.role_id
    WHERE LOWER(u.email) = LOWER(?)
    """
    rows = run_query(sql, (email,))
    return rows[0] if rows else None


def get_user_by_id(user_id: int) -> dict | None:
    sql = """
    SELECT u.id, u.email, u.full_name, u.is_active, u.must_change_password,
           r.code AS role_code
    FROM dbo.users u
    INNER JOIN dbo.roles r ON r.id = u.role_id
    WHERE u.id = ?
    """
    rows = run_query(sql, (user_id,))
    return rows[0] if rows else None


def get_modules_for_user(user_id: int) -> list[dict]:
    sql = """
    SELECT m.code, m.display_name, m.route_path
    FROM dbo.user_modules um
    INNER JOIN dbo.modules m ON m.id = um.module_id
    WHERE um.user_id = ? AND m.is_active = 1
    ORDER BY m.display_name
    """
    return run_query(sql, (user_id,))


def list_modules() -> list[dict]:
    return run_query("SELECT id, code, display_name, route_path FROM dbo.modules WHERE is_active = 1 ORDER BY display_name")


def update_login_success(user_id: int) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            UPDATE dbo.users
            SET failed_login_attempts = 0,
                locked_until = NULL,
                last_login_at = SYSUTCDATETIME(),
                updated_at = SYSUTCDATETIME()
            WHERE id = ?
            """,
            (user_id,),
        )
        cn.commit()


def update_login_failure(user_id: int, max_attempts: int, lock_minutes: int) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            UPDATE dbo.users
            SET failed_login_attempts = failed_login_attempts + 1,
                locked_until = CASE
                    WHEN failed_login_attempts + 1 >= ? THEN DATEADD(MINUTE, ?, SYSUTCDATETIME())
                    ELSE locked_until
                END,
                updated_at = SYSUTCDATETIME()
            WHERE id = ?
            """,
            (max_attempts, lock_minutes, user_id),
        )
        cn.commit()


def update_password(user_id: int, password_hash: str, must_change_password: bool) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            UPDATE dbo.users
            SET password_hash = ?,
                must_change_password = ?,
                failed_login_attempts = 0,
                locked_until = NULL,
                updated_at = SYSUTCDATETIME()
            WHERE id = ?
            """,
            (password_hash, 1 if must_change_password else 0, user_id),
        )
        cn.commit()


def create_user(email: str, full_name: str, password_hash: str, role_code: str, created_by_user_id: int | None) -> int:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute("SELECT id FROM dbo.roles WHERE code = ?", (role_code,))
        role_row = cur.fetchone()
        if not role_row:
            raise RuntimeError(f"Rol no existe: {role_code}")
        role_id = int(role_row[0])
        cur.execute(
            """
            INSERT INTO dbo.users(email, full_name, password_hash, role_id, must_change_password, created_by_user_id)
            OUTPUT INSERTED.id
            VALUES(?, ?, ?, ?, 1, ?)
            """,
            (email, full_name, password_hash, role_id, created_by_user_id),
        )
        new_id = int(cur.fetchone()[0])
        cn.commit()
        return new_id


def set_user_active(user_id: int, is_active: bool) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute("UPDATE dbo.users SET is_active = ?, updated_at = SYSUTCDATETIME() WHERE id = ?", (1 if is_active else 0, user_id))
        cn.commit()


def set_user_modules(user_id: int, module_codes: list[str], actor_user_id: int | None) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute("DELETE FROM dbo.user_modules WHERE user_id = ?", (user_id,))
        if module_codes:
            marks = ",".join("?" for _ in module_codes)
            cur.execute(f"SELECT id FROM dbo.modules WHERE code IN ({marks}) AND is_active = 1", tuple(module_codes))
            module_ids = [int(r[0]) for r in cur.fetchall()]
            for module_id in module_ids:
                cur.execute(
                    "INSERT INTO dbo.user_modules(user_id, module_id, created_by_user_id) VALUES (?, ?, ?)",
                    (user_id, module_id, actor_user_id),
                )
        cn.commit()


def list_users() -> list[dict]:
    sql = """
    SELECT u.id, u.email, u.full_name, u.is_active, u.must_change_password, r.code AS role_code
    FROM dbo.users u
    INNER JOIN dbo.roles r ON r.id = u.role_id
    ORDER BY u.id DESC
    """
    return run_query(sql)


def insert_audit(actor_user_id: int | None, action: str, target_type: str | None = None, target_id: int | None = None, detail: str | None = None) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.audit_logs(actor_user_id, action, target_type, target_id, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor_user_id, action, target_type, target_id, detail),
        )
        cn.commit()
