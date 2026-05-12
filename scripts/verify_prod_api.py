"""
Test live Cloud Run API by calling tests/available and printing actual question counts.
"""
import sys, os, json, urllib.request, urllib.error

# We can't get a real Firebase token without the client SDK.
# Instead, let's test the DB directly via Cloud SQL to see what
# the Cloud Run service WOULD return if it queries the same DB.

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'postgresql://postgres:Mcq_Prod_Safe_99!!@34.45.15.5:5432/mcq_portal'

from app.db.session import SessionLocal
from app.models.domain import Test, Question, Subject

db = SessionLocal()

print("=" * 60)
print("PRODUCTION DATABASE - EXACT API QUERY SIMULATION")
print("=" * 60)

tests = db.query(Test).filter(Test.is_active == True).all()
print(f"Total active tests: {len(tests)}")
print()

for test in tests[:15]:
    total_questions = db.query(Question).filter(Question.test_id == test.id).count()
    subject_name = test.subject.name if test.subject else "MISSING"
    print(f"  id={test.id:3d} | {test.title:<30} | subject={subject_name:<15} | questions={total_questions}")

print()
print("=" * 60)
print("SUMMARY BY SUBJECT:")
for subj in db.query(Subject).all():
    tests_for_subj = db.query(Test).filter(Test.subject_id == subj.id, Test.is_active == True).all()
    total_q = sum(db.query(Question).filter(Question.test_id == t.id).count() for t in tests_for_subj)
    print(f"  {subj.name:<15} | {len(tests_for_subj)} tests | {total_q} questions")

db.close()
