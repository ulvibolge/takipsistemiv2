from datetime import datetime, timezone
from pydantic import BaseModel, Field, constr
from typing import Optional
from bson import ObjectId


# ✅ MongoDB ObjectId ile uyumlu özel Pydantic tipi
class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)


class IssueStatus(str):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ✅ Şikayet/Kayıt Oluşturma Şeması
class IssueCreate(BaseModel):
    title: constr(min_length=3, max_length=200) = Field(..., description="Sorun başlığı")
    description: Optional[str] = Field(None, max_length=1000, description="Detaylı açıklama")
    reported_by: Optional[PyObjectId] = Field(None, description="Bildirimi yapan kullanıcı ID")
    status: Optional[str] = Field(IssueStatus.OPEN, description="Sorunun mevcut durumu")
    date_reported: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Bildirim tarihi (UTC)")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v),
        }
        json_schema_extra = {
            "example": {
                "title": "Şantiye elektrik kesintisi",
                "description": "Gece vardiyası sırasında elektrik tamamen kesildi.",
                "reported_by": "64ac72a2e8f9b8b1f5a4e123",
                "status": "open",
                "date_reported": "2024-04-03T20:45:00Z"
            }
        }


# ✅ Veritabanından dönen çıktı şeması
class IssueOut(IssueCreate):
    id: PyObjectId = Field(..., alias="_id", description="Issue kayıt ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Kayıt oluşturulma tarihi")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Kayıt güncellenme tarihi")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v),
        }
        json_schema_extra = {
            "example": {
                "_id": "65ac77e2a8f2b4c2c0d8a11e",
                "title": "Şantiye elektrik kesintisi",
                "description": "Gece vardiyası sırasında elektrik tamamen kesildi.",
                "reported_by": "64ac72a2e8f9b8b1f5a4e123",
                "status": "open",
                "date_reported": "2024-04-03T20:45:00Z",
                "created_at": "2024-04-03T20:50:00Z",
                "updated_at": "2024-04-03T21:10:00Z"
            }
        }
