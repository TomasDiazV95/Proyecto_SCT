from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from repositories.session_control_repo import invalidate_all_sessions  # noqa: E402
from repositories.users_repo import insert_audit  # noqa: E402


def main() -> None:
    invalidate_all_sessions(None)
    insert_audit(None, "LOGOUT_ALL_USERS", "session", None, "scheduled_or_manual")
    print("Sesiones invalidadas correctamente.")


if __name__ == "__main__":
    main()
