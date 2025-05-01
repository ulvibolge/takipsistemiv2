"""
Client modeli, sisteme kayıtlı müşteri firmaları temsil eder.
Her müşteri bir tenant'a (organizasyon) bağlıdır ve sistem üzerinden projeleri takip eder.

- `created_at` ve `updated_at` alanları otomatik UTC zamanlıdır
- MongoDB için `_id` alanı ObjectId ile uyumludur
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId

class PyObjectId(str):
    """MongoDB ObjectId desteği"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)


class Client(BaseModel):
    """MongoDB'deki müşteri kaydı modelidir"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    company_name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    tenant_id: PyObjectId
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: str
        }
