from database import get_connection, run_query


def create_reset_token(user_id: int, token_hash: str, expires_minutes: int) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.password_reset_tokens(user_id, token_hash, expires_at)
            VALUES (?, ?, DATEADD(MINUTE, ?, SYSUTCDATETIME()))
            """,
            (user_id, token_hash, expires_minutes),
        )
        cn.commit()


def get_valid_token(user_id: int, token_hash: str) -> dict | None:
    sql = """
    SELECT TOP 1 id, user_id, expires_at, used_at
    FROM dbo.password_reset_tokens
    WHERE user_id = ?
      AND token_hash = ?
      AND used_at IS NULL
      AND expires_at >= SYSUTCDATETIME()
    ORDER BY id DESC
    """
    rows = run_query(sql, (user_id, token_hash))
    return rows[0] if rows else None


def mark_user_tokens_used(user_id: int) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            UPDATE dbo.password_reset_tokens
            SET used_at = SYSUTCDATETIME()
            WHERE user_id = ?
              AND used_at IS NULL
            """,
            (user_id,),
        )
        cn.commit()


def mark_token_used(token_id: int) -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute("UPDATE dbo.password_reset_tokens SET used_at = SYSUTCDATETIME() WHERE id = ?", (token_id,))
        cn.commit()
