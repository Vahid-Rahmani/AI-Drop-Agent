"""Fail-fast validation for live deployment configuration."""

from app.core.config import Settings


def main() -> int:
    settings = Settings()
    errors = settings.production_errors()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Production configuration is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

