"""
client.py

Bu dosya, sistemdeki "müşteri" (Client) nesnesine ait Pydantic şemalarını içerir. Bu şemalar, müşterilerin
oluşturulması, güncellenmesi, görüntülenmesi gibi işlemlerde kullanılır. Tüm modeller Pydantic V2 standartlarına
uygun hale getirilmiş ve geliştiriciler için örnek JSON yapıları eklenmiştir.

- `ClientCreate`: Yeni müşteri oluşturmak için kullanılan giriş şeması.
- `ClientUpdate`: Mevcut bir müşteriyi güncellemek için kullanılan şema.
- `ClientOut`: API üzerinden dönen müşteri verisinin dışa aktarım şeması.
- `ClientInDB`: Veritabanı içindeki müşteri temsili.

Ayrıca tüm modellerde `datetime.now(timezone.utc)` kullanılarak UTC tabanlı zaman damgaları tanımlanmıştır.
"""

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId
datetime.now(timezone.utc)  # UTC zaman dilimini kullanmak için
class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)

class ClientBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr = Field(...)
    phone: Optional[str] = Field(None, max_length=20)
    permissions: Optional[List[str]] = Field(default_factory=list)

class ClientCreate(ClientBase):
    pass

class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    permissions: Optional[List[str]] = None

class ClientOut(ClientBase):
    id: PyObjectId = Field(..., alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v)
        }
        json_schema_extra = {
            "example": {
                "_id": "64f8d2e9f1a4e5f3a1234567",
                "name": "ABC Mühendislik",
                "email": "abc@example.com",
                "phone": "+905551112233",
                "permissions": ["view_projects", "create_request"],
                "created_at": "2024-01-01T10:00:00Z",
                "updated_at": "2024-03-01T12:00:00Z"
            }
        }

class ClientInDB(ClientOut):
    hashed_secret: Optional[str] = Field(None, description="Gizli anahtar hash")
