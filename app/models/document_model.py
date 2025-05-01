"""
Bu dosya, yüklenen evrakların MongoDB'deki modelini tanımlar.

- Evraklar, projelere veya personele ilişkilendirilebilir.
- Dosya türü, açıklama, ekleyen kullanıcı ve zaman damgaları gibi alanlar içerir.
- Tüm zamanlar UTC formatında kaydedilir.
"""

from datetime import datetime, timezone
from typing import Optional
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


class Document(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    file_name: str = Field(..., max_length=255, description="Dosya adı")
    file_type: str = Field(..., max_length=50, description="Dosya uzantısı (pdf, jpg, png, docx, vb.)")
    file_url: str = Field(..., description="Sunucudaki dosya yolu veya URL")
    uploaded_by: PyObjectId = Field(..., description="Dosyayı yükleyen kullanıcı ID")
    related_project_id: Optional[PyObjectId] = Field(None, description="İlgili proje ID")
    related_personnel_id: Optional[PyObjectId] = Field(None, description="İlgili personel ID")
    description: Optional[str] = Field(None, max_length=500, description="Açıklama veya etiket")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Yüklenme tarihi")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Güncellenme tarihi")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: str
        }
