import os
import sys

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.core.gs.models import GsSubject

def main():
    db = SessionLocal()
    try:
        # Check if subject with ID 1 exists
        subject = db.query(GsSubject).filter(GsSubject.id == 1).first()
        if not subject:
            print("Subject with ID 1 not found. Creating 'Geography' subject...")
            subject = GsSubject(
                id=1,
                slug="geography",
                name="Geography",
                description="General Studies Geography Curriculum",
                is_complete=True
            )
            db.add(subject)
            db.commit()
            print("Successfully seeded Geography subject (ID=1).")
        else:
            print("Geography subject (ID=1) already exists.")
    except Exception as e:
        db.rollback()
        print("ERROR:", e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
