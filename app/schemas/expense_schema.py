from datetime import datetime, date, timezone
from pydantic import BaseModel, Field, field_validator, condecimal, constr
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

class ExpenseCategory(str, Enum):
    labor = "labor"
    material = "material"
    transport = "transport"
    equipment = "equipment"
    misc = "misc"

class ExpenseCreate(BaseModel):
    category: ExpenseCategory = Field(..., description="Masraf kategorisi")
    amount: condecimal(gt=0, max_digits=10, decimal_places=2) = Field(
        ...,
        example=1200.75,
        description="Pozitif değer (max 10 digit, 2 decimal)"
    )
    currency: constr(pattern=r'^[A-Z]{3}$', max_length=3) = Field(
        "TRY",
        example="USD",
        description="ISO 4217 para birimi kodu"
    )
    date: date = Field(..., example="2024-03-20")
    description: Optional[str] = Field(None, max_length=300)
    project_id: PyObjectId = Field(..., example="64d72c9a1ef2c001f73e999b")
    invoice_number: Optional[str] = Field(None, max_length=50)
    invoice_date: Optional[date] = Field(None)

class ExpenseUpdate(BaseModel):
    amount: Optional[condecimal(gt=0, max_digits=10, decimal_places=2)] = None
    date: Optional[date] = None
    description: Optional[str] = Field(None, max_length=300)
    invoice_number: Optional[str] = Field(None, max_length=50)
    invoice_date: Optional[date] = None

class ExpenseOut(ExpenseCreate):
    id: PyObjectId = Field(..., example="64e8f8c7a1ef2c001f12a888")
    is_approved: bool = Field(default=False)
    approved_by: Optional[PyObjectId] = Field(None)
    approval_date: Optional[datetime] = Field(None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('updated_at', mode='before')
    @classmethod
    def set_updated_at(cls, v):
        return v or datetime.now(timezone.utc)

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v)
        }
        json_schema_extra = {
            "examples": {
                "approved": {
                    "value": {
                        "id": "64e8f8c7a1ef2c001f12a888",
                        "category": "material",
                        "amount": 4500.00,
                        "currency": "USD",
                        "date": "2024-03-15",
                        "description": "Çelik profil alımı",
                        "project_id": "64d72c9a1ef2c001f73e999b",
                        "invoice_number": "INV-2024-015",
                        "is_approved": True,
                        "approved_by": "64a1b2c3d4e5f67890123456",
                        "created_at": "2024-03-16T09:30:00Z",
                        "updated_at": "2024-03-18T14:25:00Z"
                    }
                },
                "pending": {
                    "value": {
                        "category": "labor",
                        "amount": 8250.50,
                        "date": "2024-03-20",
                        "project_id": "64d72c9a1ef2c001f73e999b"
                    }
                }
            }
        }
