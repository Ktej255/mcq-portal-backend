from app.db.session import Base
from app.models.domain import User, Subject, Topic, Test, Question, Attempt, AttemptAnswer, Report

# Register the UPSC Optional Subjects Platform models on the shared metadata so
# they are discoverable for Alembic autogenerate. Importing here ensures the
# tables are present in Base.metadata whenever the models package is loaded
# (alembic env.py imports app.models.domain, which loads this package first).
from app.core.optional import models as optional_models  # noqa: F401
from app.core.optional import student_models as optional_student_models  # noqa: F401

# Register the GS (General Studies) content models on the shared metadata too
# (Master Plan A3/B3, GATE-1). Importing here keeps ``gs_*`` tables present in
# Base.metadata for Alembic autogenerate and the in-memory create_all in tests.
from app.core.gs import models as gs_models  # noqa: F401

# For alembic autogenerate
