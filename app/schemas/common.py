from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Operation successful"
    data: Optional[T] = None
    
class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Operation successful"
    data: list[T]
    total: int
    page: int
    size: int
