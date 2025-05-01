from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from enum import Enum
from bson import ObjectId


class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)


class SubcontractorType(str, Enum):
    electrical = "electrical"
    plumbing = "plumbing"
    construction = "construction"
    other = "other"


class SubcontractorCreate(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=100)
    contact_person: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[1-9]\d{1,14}$")
    email: Optional[EmailStr] = None
    subcontractor_type: SubcontractorType
    assigned_project_id: str
    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None
    is_responsible_for_costs: bool = False


class SubcontractorUpdate(BaseModel):
    contact_person: Optional[str] = Field(None, min_length=2)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    email: Optional[EmailStr] = None
    contract_end_date: Optional[datetime] = None
    is_responsible_for_costs: Optional[bool] = None


class SubcontractorOut(SubcontractorCreate):
    id: PyObjectId
    current_status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v)
        },
        "json_schema_extra": {
            "example": {
                "id": "60af8849f1a4e00d9c9c1d11",
                "company_name": "Elektrik Yapı A.Ş.",
                "contact_person": "Mehmet Kaya",
                "phone": "+905551234567",
                "email": "mehmet@elektrikyapi.com",
                "subcontractor_type": "electrical",
                "assigned_project_id": "645af8849f1a4e00d9c9c1b9",
                "contract_start_date": "2024-01-01T09:00:00Z",
                "contract_end_date": "2024-12-31T18:00:00Z",
                "is_responsible_for_costs": True,
                "current_status": "active",
                "created_at": "2024-01-01T09:00:00Z",
                "updated_at": "2024-03-01T12:00:00Z"
            }
        }
    }
