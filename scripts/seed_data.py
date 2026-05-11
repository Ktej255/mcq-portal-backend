import os
import sys
import json
from datetime import datetime, timezone

# Add the parent directory to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine
from app.models.domain import Base, User, RoleEnum, Subject, Topic, Test, Question

def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def seed():
    print("Seeding database...")
    db = SessionLocal()
    
    try:
        # Create Admin
        admin = User(
            google_uid="admin_mock_uid_123",
            email="admin@mcq.com",
            full_name="Admin User",
            role=RoleEnum.ADMIN
        )
        # Create Student
        student = User(
            google_uid="student_mock_uid_456",
            email="student@mcq.com",
            full_name="Student User",
            role=RoleEnum.STUDENT
        )
        db.add_all([admin, student])
        db.commit()

        # Create Subject
        physics = Subject(name="Physics")
        maths = Subject(name="Mathematics")
        db.add_all([physics, maths])
        db.commit()
        db.refresh(physics)
        db.refresh(maths)

        # Create Topics
        kinematics = Topic(name="Kinematics", subject_id=physics.id)
        thermo = Topic(name="Thermodynamics", subject_id=physics.id)
        algebra = Topic(name="Algebra", subject_id=maths.id)
        db.add_all([kinematics, thermo, algebra])
        db.commit()
        db.refresh(kinematics)

        # Create Test
        test1 = Test(
            title="Physics Mock Test 1",
            description="Comprehensive kinematics and thermodynamics mock test.",
            subject_id=physics.id,
            duration_minutes=30,
            correct_marks=4.0,
            negative_marking_value=1.0,
            is_active=True
        )
        db.add(test1)
        db.commit()
        db.refresh(test1)

        # Create Questions
        q1 = Question(
            test_id=test1.id,
            topic_id=kinematics.id,
            text_en="A car accelerates from rest at a constant rate of 2 m/s² for 5 seconds. What is its final velocity?",
            text_hi="एक कार विश्राम अवस्था से 2 m/s² की स्थिर दर से 5 सेकंड तक त्वरित होती है। इसका अंतिम वेग क्या है?",
            options_en={"A": "5 m/s", "B": "10 m/s", "C": "15 m/s", "D": "20 m/s"},
            options_hi={"A": "5 m/s", "B": "10 m/s", "C": "15 m/s", "D": "20 m/s"},
            correct_option="B",
            difficulty="EASY"
        )
        
        q2 = Question(
            test_id=test1.id,
            topic_id=kinematics.id,
            text_en="Which of the following is a scalar quantity?",
            text_hi="निम्नलिखित में से कौन सी एक अदिश राशि है?",
            options_en={"A": "Velocity", "B": "Acceleration", "C": "Speed", "D": "Displacement"},
            options_hi={"A": "वेग", "B": "त्वरण", "C": "चाल", "D": "विस्थापन"},
            correct_option="C",
            difficulty="EASY"
        )

        db.add_all([q1, q2])
        db.commit()
        
        print("Database seeded successfully.")
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_db()
    seed()
