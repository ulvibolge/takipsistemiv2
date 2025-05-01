"""
Bu model dosyası, sahada kullanılan tüm malzemelerin MongoDB'de nasıl temsil edildiğini açıklar.

- Malzeme bilgileri, proje ile ilişkilendirilir.
- Malzeme hareketleri (giriş/çıkış) ve stok durumları takip edilebilir.
- Fiyat, miktar ve para birimi gibi detaylar da tutulur.
- Tüm zamanlar UTC formatında kaydedilir.
"""

from datetime import datetime, date, timezone
from typing import Optional, List, Literal
from decimal import Decimal
from pydantic import BaseModel, Field
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


class MaterialTransaction(BaseModel):
    transaction_type: Literal["in", "out"] = Field(..., description="İşlem tipi: in (giriş), out (çıkış)")
    amount: Decimal = Field(..., gt=0, description="Malzeme miktarı")
    date: date = Field(default_factory=date.today, description="İşlem tarihi")
    performed_by: PyObjectId = Field(..., description="İşlemi gerçekleştiren kullanıcı ID")
    notes: Optional[str] = Field(None, max_length=300, description="Açıklama (opsiyonel)")

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            ObjectId: str
        }


class Material(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=2, max_length=100, description="Malzeme adı")
    category: str = Field(..., description="Malzeme kategorisi")
    quantity: Decimal = Field(..., gt=0, description="Toplam miktar")
    unit: str = Field(..., description="Birim (kg, m, adet vb.)")
    min_stock_level: Decimal = Field(default=Decimal('0'), description="Minimum stok seviyesi")
    supplier: Optional[str] = Field(None, max_length=100, description="Tedarikçi firma adı")
    unit_price: Optional[Decimal] = Field(None, gt=0, description="Birim fiyat (opsiyonel)")
    currency: str = Field(default="TRY", regex=r"^[A-Z]{3}$", max_length=3, description="Para birimi (ISO 4217)")
    project_id: PyObjectId = Field(..., description="İlgili proje ID")
    notes: Optional[str] = Field(None, max_length=500, description="Açıklama (opsiyonel)")
    current_value: Optional[Decimal] = Field(None, description="Stok değeri (miktar x birim fiyat)")
    is_low_stock: bool = Field(default=False, description="Stok yetersiz mi?")
    transactions: List[MaterialTransaction] = Field(default_factory=list, max_items=1000, description="İşlem geçmişi")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Kayıt tarihi")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Güncelleme tarihi")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            Decimal: str,
            ObjectId: str
        }
