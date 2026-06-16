from typing import Optional

from pydantic import BaseModel


class CreateOrderIn(BaseModel):
    tier: str
    cycle: str = "monthly"
    phone: Optional[str] = None


class CreateOrderOut(BaseModel):
    order_id: str
    payment_session_id: str
    amount: int
    currency: str = "INR"
    env: str
