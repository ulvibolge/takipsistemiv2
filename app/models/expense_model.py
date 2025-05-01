"""
Bu dosya, MongoDB'de saklanan masraf (expense) kayıtlarını temsil eden Pydantic V2 uyumlu model tanımını içerir.

- Her masraf, proje ID'si ile ilişkilidir.
- Onay durumu, fatura bilgileri ve oluşturulma/güncellenme zamanları gibi alanları içerir.
- Pydantic'in `ConfigDict` sınıfı ile JSON dönüşüm kuralları ve schema örnekleri tanımlanmıştır.
"""

from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
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


class Expense(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    category: ExpenseCategory = Field(..., description="Masraf kategorisi")
    amount: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2, description="Pozitif masraf tutarı")
    currency: str = Field("TRY", min_length=3, max_length=3, pattern=r'^[A-Z]{3}$', description="Para birimi kodu (ISO 4217)")
    date: date = Field(..., description="Masraf tarihi")
    description: Optional[str] = Field(None, max_length=300, description="Masraf açıklaması")
    project_id: PyObjectId = Field(..., description="Masrafın ait olduğu proje ID")
    invoice_number: Optional[str] = Field(None, max_length=50, description="Fatura numarası")
    invoice_date: Optional[date] = Field(None, description="Fatura tarihi")
    is_approved: bool = Field(default=False, description="Masraf onay durumu")
    approved_by: Optional[PyObjectId] = Field(None, description="Onaylayan kullanıcı ID")
    approval_date: Optional[datetime] = Field(None, description="Onay tarihi")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Kayıt oluşturulma zamanı")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Son güncellenme zamanı")

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            Decimal: lambda v: str(v),
            ObjectId: str,
        },
        json_schema_extra={
            "example": {
                "_id": "64e8f8c7a1ef2c001f12a888",
                "category": "material",
                "amount": "4500.00",
                "currency": "USD",
                "date": "2024-03-15",
                "description": "Çelik profil alımı",
                "project_id": "64d72c9a1ef2c001f73e999b",
                "invoice_number": "INV-2024-015",
                "invoice_date": "2024-03-15",
                "is_approved": True,
                "approved_by": "64a1b2c3d4e5f67890123456",
                "approval_date": "2024-03-16T09:30:00Z",
                "created_at": "2024-03-16T09:30:00Z",
                "updated_at": "2024-03-18T14:25:00Z"
            }
        }
    )
