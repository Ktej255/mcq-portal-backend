from sqlalchemy import Column, DateTime, Boolean, String
from datetime import datetime, timezone
from sqlalchemy.orm import declarative_mixin

@declarative_mixin
class InstitutionalAuditMixin:
    """
    Standard institutional audit trail for educational records.
    """
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(String, nullable=True) # System Actor or User ID
    updated_by = Column(String, nullable=True)

@declarative_mixin
class SoftDeleteMixin:
    """
    Enforces data preservation requirements. 
    Educational records must not be hard-deleted for institutional audits.
    """
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    def soft_delete(self, db_session, actor=None):
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        if hasattr(self, 'updated_by'):
            self.updated_by = actor
        db_session.add(self)
