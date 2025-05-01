from datetime import datetime, date, timezone
from pydantic import BaseModel, Field, EmailStr, field_validator, constr
from typing import Optional, List
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

class PersonnelRole(str, Enum):
    engineer = "engineer"
    technician = "technician"
    foreman = "foreman"
    worker = "worker"
    admin = "admin"

class PersonnelBase(BaseModel):
    full_name: constr(min_length=2, max_length=100) = Field(...)
    role: PersonnelRole = Field(...)
    identity_number: Optional[constr(min_length=11, max_length=11)] = Field(None)
    phone: Optional[constr(pattern=r"^\+?[1-9]\d{1,14}$")] = Field(None)
    email: Optional[EmailStr] = Field(None)
    start_date: Optional[date] = Field(None)
    assigned_project_id: Optional[PyObjectId] = Field(None)
    nfc_card_id: Optional[constr(pattern=r'^[A-F0-9]{12,14}$')] = Field(None)
    is_active: bool = Field(default=True)
    permissions: List[str] = Field(default_factory=list)
    notes: Optional[str] = Field(None)

    @field_validator('identity_number')
    @classmethod
    def validate_identity_number(cls, v):
        if v:
            if not v.isdigit() or len(v) != 11 or int(v[0]) == 0 or int(v[-1]) % 2 != 0:
                raise ValueError('Geçersiz TCKN formatı')
        return v

    @field_validator('start_date')
    @classmethod
    def validate_start_date(cls, v):
        if v and v > date.today():
            raise ValueError('Başlangıç tarihi bugünden sonra olamaz')
        return v

class PersonnelCreate(PersonnelBase):
    model_config = {
        "json_encoders": {
            date: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v)
        },
        "json_schema_extra": {
            "examples": {
                "technician": {
                    "value": {
                        "full_name": "Ahmet Yılmaz",
                        "role": "technician",
                        "phone": "+905551234567",
                        "is_active": True
                    }
                }
            }
        }
    }

class PersonnelUpdate(BaseModel):
    full_name: Optional[constr(min_length=2, max_length=100)] = None
    role: Optional[PersonnelRole] = None
    phone: Optional[constr(pattern=r"^\+?[1-9]\d{1,14}$")] = None
    email: Optional[EmailStr] = None
    start_date: Optional[date] = None
    assigned_project_id: Optional[PyObjectId] = None
    nfc_card_id: Optional[constr(pattern=r'^[A-F0-9]{12,14}$')] = None
    is_active: Optional[bool] = None
    permissions: Optional[List[str]] = None
    notes: Optional[str] = None

    @field_validator('start_date')
    @classmethod
    def validate_update_start_date(cls, v):
        if v and v > date.today():
            raise ValueError('Başlangıç tarihi bugünden sonra olamaz')
        return v

class PersonnelOut(PersonnelBase):
    id: PyObjectId = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('updated_at', mode="before")
    @classmethod
    def set_updated_at(cls, v):
        return v or datetime.now(timezone.utc)

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(), 
            ObjectId: lambda v: str(v)
        }
    }
