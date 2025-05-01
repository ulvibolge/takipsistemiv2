"""
document.py

📄 Bu dosya, sistemdeki döküman yönetimi ile ilgili tüm Pydantic şemalarını içerir.
Sistem mimarisinin geri kalan modülleriyle entegre çalışmak üzere aşağıdaki yapılar tanımlanmıştır:

🔹 MongoDB uyumlu ObjectId doğrulama desteği (`PyObjectId`)
🔹 Döküman oluşturma ve güncelleme şemaları
🔹 Dosya tipi Enum tanımı (`DocumentType`)
🔹 Kullanıcı, proje ve tenant ID’lerine bağlanabilen yapı
🔹 UTC bazlı timestamp alanları (created_at, updated_at)
🔹 Swagger için örnekler ve `json_encoders` ile ISO tarih formatlaması

🛠 Bu yapı, dosya kayıtlarının kullanıcıya ait olduğunu ve sistemsel düzenlemeler (ör: döküman tipi, proje bağlantısı)
gibi bilgileri içerir. `document_out` yapısı ise veritabanı modelini dışa aktarmada kullanılır.
"""

from datetime import datetime, timezone
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field
from bson import ObjectId

# ✅ MongoDB ObjectId ile uyumlu özel Pydantic tipi
class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Geçersiz ObjectId formatı")
        return str(v)

# ✅ Döküman tipleri için enum tanımı
class DocumentType(str, Enum):
    contract = "contract"
    invoice = "invoice"
    delivery_note = "delivery_note"
    photo = "photo"
    other = "other"

# ✅ Yeni döküman yüklemek için kullanılacak şema
class DocumentCreate(BaseModel):
    filename: str = Field(..., description="Dosya adı (ör: teklif.pdf)", max_length=200)
    content_type: str = Field(..., description="Dosya içeriği türü (ör: application/pdf)")
    size: int = Field(..., gt=0, description="Dosya boyutu (byte cinsinden)")
    type: DocumentType = Field(..., description="Döküman tipi (fatura, sözleşme, vb.)")
    uploaded_by: PyObjectId = Field(..., description="Yükleyen kullanıcı ID")
    project_id: Optional[PyObjectId] = Field(None, description="İlgili proje ID (opsiyonel)")
    tenant_id: Optional[PyObjectId] = Field(None, description="Bağlı olduğu firma (tenant) ID (opsiyonel)")
    description: Optional[str] = Field(None, max_length=300, description="Döküman açıklaması")

# ✅ Döküman güncelleme işlemleri için kullanılacak şema
class DocumentUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=300, description="Güncel açıklama")
    type: Optional[DocumentType] = Field(None, description="Döküman tipi güncellemesi")

# ✅ Veritabanından çıkan verileri temsil eden döküman modeli
class DocumentOut(DocumentCreate):
    id: PyObjectId = Field(..., alias="_id")
    path: str = Field(..., description="Dosyanın sistem içindeki tam yolu")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Yükleme zamanı")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Son güncelleme zamanı")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v),
        }
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "_id": "64e8f8c7a1ef2c001f12a888",
                "filename": "teklif.pdf",
                "content_type": "application/pdf",
                "size": 542132,
                "type": "contract",
                "uploaded_by": "64d72c9a1ef2c001f73e999b",
                "project_id": "64a1b2c3d4e5f67890123456",
                "tenant_id": "64ac72a2e8f9b8b1f5a4e123",
                "description": "X projesine ait teklif dosyası",
                "path": "/files/64e8f8c7a1ef2c001f12a888_teklif.pdf",
                "created_at": "2024-03-15T09:00:00Z",
                "updated_at": "2024-03-15T09:00:00Z"
            }
        }
