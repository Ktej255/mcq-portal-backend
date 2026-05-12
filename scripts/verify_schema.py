import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import engine
from app.services.schema_integrity import collect_schema_drift


def main() -> int:
    drift = collect_schema_drift(engine)
    if drift:
        print("SCHEMA DRIFT DETECTED")
        for table, missing in drift.items():
            print(f"{table}: {', '.join(missing)}")
        return 1
    print("SCHEMA OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
