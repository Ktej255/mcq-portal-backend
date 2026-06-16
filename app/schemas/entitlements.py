from typing import Optional

from pydantic import BaseModel


class Entitlements(BaseModel):
    tier: str
    label: str
    daily_mcq_limit: Optional[int] = None
    daily_ai_minutes: Optional[int] = None
    weak_topic_runs: Optional[int] = None
    optional_subjects: bool
    mains_upload: bool
    unlimited_tests: bool
    all_subjects: bool
