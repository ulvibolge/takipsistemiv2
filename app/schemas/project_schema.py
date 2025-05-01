from datetime import datetime, date, timezone
from pydantic import BaseModel, Field, field_validator, conlist
from typing import Optional
from enum import Enum
from bson import ObjectId

# ✅ UTC zamanı default olarak kullanabilmek için fonksiyon
def now_utc():
    return datetime.now(timezone.utc)

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

# ✅ Proje durumu enum'u – Swagger UI'da kullanıcıya seçim menüsü olarak sunulur
class ProjectStatus(str, Enum):
    planning = "planning"
    ongoing = "ongoing"
    completed = "completed"
    cancelled = "cancelled"

# ✅ Yeni proje oluşturulurken kullanılan şema
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100, example="X Fabrikası Elektrik Altyapı")
    description: Optional[str] = Field(None, max_length=500, example="Yüksek gerilim sistemleri kurulumu")
    start_date: date = Field(..., example="2024-01-15")
    end_date: Optional[date] = Field(None, example="2024-06-30")
    budget: Optional[float] = Field(None, gt=0, example=150000.0)
    location: Optional[str] = Field(None, max_length=200, example="Gebze OSB, Kocaeli")
    client_id: Optional[PyObjectId] = Field(None, example="64ac72a2e8f9b8b1f5a4e123")

# ✅ Listelerde max eleman sayısı için `conlist` tanımı
AssignedList = conlist(item_type=PyObjectId, max_length=100)
SubcontractorList = conlist(item_type=PyObjectId, max_length=50)

# ✅ Proje güncelleme işlemleri için opsiyonel alanlardan oluşan şema
class ProjectUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=500)
    end_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
    budget: Optional[float] = Field(None, gt=0)

# ✅ Projeyi dışa dönerken kullanılan gelişmiş şema
class ProjectOut(ProjectCreate):
    id: PyObjectId = Field(..., example="507f1f77bcf86cd799439011")
    status: ProjectStatus = Field(ProjectStatus.planning, description="Projenin mevcut durumu")
    assigned_personnel: AssignedList = Field(default_factory=list, description="Projede görevli personel ID listesi")
    subcontractors: SubcontractorList = Field(default_factory=list, description="Projede çalışan taşeron firma ID listesi")
    created_at: datetime = Field(default_factory=now_utc, description="Kayıt oluşturulma tarihi (UTC)")
    updated_at: datetime = Field(default_factory=now_utc, description="Son güncellenme tarihi (UTC)")
    completion_percentage: float = Field(0.0, ge=0, le=100, description="Projenin tamamlanma yüzdesi (0-100 arası)")

    @field_validator('updated_at', mode='before')
    @classmethod
    def set_updated_at(cls, v):
        return v or now_utc()

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat(),
            ObjectId: lambda v: str(v)
        }
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "X Fabrikası Elektrik Altyapı",
                "description": "Yüksek gerilim ve zayıf akım sistemlerinin kurulumu",
                "start_date": "2024-01-15",
                "end_date": "2024-06-30",
                "budget": 150000.0,
                "location": "Gebze OSB, Kocaeli",
                "client_id": "64ac72a2e8f9b8b1f5a4e123",
                "status": "ongoing",
                "assigned_personnel": ["64bb32c9a1ef2c001f73e999"],
                "subcontractors": ["64cc32c9a1ef2c001f55e777"],
                "created_at": "2024-01-10T08:00:00Z",
                "updated_at": "2024-04-01T12:00:00Z",
                "completion_percentage": 45.0
            }
        }
