from datetime import datetime, timezone

from database import get_connection, run_query


def ensure_session_control_table() -> None:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            IF OBJECT_ID('dbo.auth_session_control', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.auth_session_control (
                    id INT NOT NULL CONSTRAINT PK_auth_session_control PRIMARY KEY,
                    tokens_valid_after DATETIME2 NOT NULL,
                    updated_by_user_id INT NULL,
                    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                    CONSTRAINT CK_auth_session_control_singleton CHECK (id = 1),
                    CONSTRAINT FK_auth_session_control_updated_by FOREIGN KEY (updated_by_user_id) REFERENCES dbo.users(id)
                );
            END;

            IF NOT EXISTS (SELECT 1 FROM dbo.auth_session_control WHERE id = 1)
            BEGIN
                INSERT INTO dbo.auth_session_control(id, tokens_valid_after, updated_by_user_id)
                VALUES (1, CONVERT(DATETIME2, '1970-01-01T00:00:00'), NULL);
            END;
            """
        )
        cn.commit()


def get_tokens_valid_after() -> datetime:
    ensure_session_control_table()
    rows = run_query(
        "SELECT tokens_valid_after FROM dbo.auth_session_control WHERE id = 1"
    )
    value = rows[0]["tokens_valid_after"] if rows else None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def invalidate_all_sessions(updated_by_user_id: int | None = None) -> None:
    ensure_session_control_table()
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            """
            UPDATE dbo.auth_session_control
            SET tokens_valid_after = SYSUTCDATETIME(),
                updated_by_user_id = ?,
                updated_at = SYSUTCDATETIME()
            WHERE id = 1
            """,
            (updated_by_user_id,),
        )
        cn.commit()
