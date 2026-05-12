from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.domain import User, RoleEnum

def check_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"Found {len(users)} users.")
        for user in users:
            print(f"ID: {user.id} | Email: {user.email} | Role: {user.role} | UID: {user.google_uid}")
    finally:
        db.close()

if __name__ == "__main__":
    check_users()
