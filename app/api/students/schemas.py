from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = None
    department: Optional[str] = None
    gpa: Optional[float] = Field(default=None, ge=0.0, le=4.0)
    tenant_id: Optional[str] = None


class StudentUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    gpa: Optional[float] = Field(default=None, ge=0.0, le=4.0)


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    department: Optional[str] = None
    gpa: Optional[float] = None
    tenant_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
