"""Initialize the configured production store before the API starts."""

from app.core.config import Settings
from app.core.postgres import PostgresStore


def main() -> int:
    settings = Settings()
    if settings.database_url.startswith(("postgresql://", "postgres://")):
        PostgresStore(settings.database_url)
        print("PostgreSQL schema initialized.")
    else:
        print("SQLite development store selected; no external migration required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

