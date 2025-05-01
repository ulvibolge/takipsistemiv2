"""
Tenant Schema Modülü – Takip Sistemi
-------------------------------------

Bu dosya, sistemdeki firmalara (tenant) ait veri yapılarını tanımlar.

📌 Kapsadığı Modeller:
- TenantCreate: Yeni firma oluşturma için giriş modeli
- TenantUpdate: Mevcut firma güncelleme modeli
- TenantOut: API çıktısı olarak gönderilen detaylı model
- TenantList: Listeleme cevap modeli
- LicenseType: Lisans türü enum
- PhoneNumber: Telefon numarası için özel doğrulama
- PyObjectId: MongoDB ObjectId için Pydantic desteği

🧾 Not:
- `tax_number` alanı zorunludur ve benzersizdir. Aynı vergi numarasına sahip iki firma kayıt edilemez.
- `company_name` alanı ise benzersiz değildir (aynı isimli firmalar olabilir).
- Pydantic v2 standartlarına tam uyumludur.

"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any, Annotated
from enum import Enum
from bson import ObjectId
from pydantic.functional_validators import AfterValidator
from pydantic_core import core_schema

# ObjectId desteği için özel Pydantic türü
class PyObjectId(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, _: Any, __: Any):
        return core_schema.with_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(),
    )


    @classmethod
    def validate(cls, v, info):
        if not ObjectId.is_valid(v):
            raise ValueError("Geçersiz ObjectId")
        return str(v)

# Lisans türleri
class LicenseType(str, Enum):
    basic = "basic"
    premium = "premium"

# Telefon doğrulayıcı
def validate_phone_number(v: str) -> str:
    import re
    if not re.match(r"^\+?[1-9]\d{1,14}$", v):
        raise ValueError("E.164 telefon numarası formatı geçersiz")
    return v

PhoneNumber = Annotated[str, AfterValidator(validate_phone_number)]

# Tenant Oluşturma Şeması
class TenantCreate(BaseModel):
    tax_number: str = Field(..., min_length=10, max_length=15, description="Vergi numarası (benzersiz)")
    company_name: str = Field(..., min_length=2, max_length=100)
    contact_email: EmailStr
    phone: Optional[PhoneNumber] = Field(
        None,
        description="E.164 telefon numarası formatı"
    )
    license_type: LicenseType = LicenseType.basic
    max_users: int = Field(10, gt=0, le=100, description="Maksimum kullanıcı sayısı")
    subscription_type: Optional[str] = Field("free", description="Abonelik tipi")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Tenant ayarları")

# Güncelleme Modeli
class TenantUpdate(BaseModel):
    company_name: Optional[str] = Field(None, min_length=2, max_length=100)
    contact_email: Optional[EmailStr] = None
    phone: Optional[PhoneNumber] = Field(
        None,
        description="E.164 telefon numarası formatı"
    )
    license_type: Optional[LicenseType] = None
    max_users: Optional[int] = Field(None, gt=0, le=100)
    subscription_type: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

# API Dönüş Modeli
class TenantOut(TenantCreate):
    id: PyObjectId = Field(..., alias="_id")
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    database_name: str = Field(..., pattern=r"^[a-z0-9_]+$")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v)
        },
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "_id": "507f1f77bcf86cd799439011",
                "tax_number": "1234567890",
                "company_name": "Acme Inc.",
                "contact_email": "info@acme.com",
                "phone": "+905551234567",
                "license_type": "basic",
                "max_users": 10,
                "is_active": True,
                "created_at": "2023-07-01T12:00:00Z",
                "database_name": "acme_inc",
                "subscription_type": "free",
                "settings": {"language": "tr"}
            }
        }
    }

# Sayfalı Listeleme Çıktısı
class TenantList(BaseModel):
    items: List[TenantOut]
    total: int
    page: int
    size: int
