"""
Bu dosya, kullanıcılarla ilgili Pydantic şemalarını tanımlar ve kullanıcı verilerinin doğrulanması, işlenmesi 
ve API giriş/çıkış işlemleri için kullanılır. Aşağıdaki işlevleri yerine getirir:

- Kullanıcı Rolleri ve ID Doğrulama: `UserRole` enum sınıfı, kullanıcı rollerini tanımlar. `PyObjectId` sınıfı, 
  MongoDB ObjectId doğrulaması için kullanılır.
- Kullanıcı Şemaları: Kullanıcı oluşturma, güncelleme, giriş ve şifre sıfırlama gibi işlemler için farklı şemalar 
  tanımlanmıştır (`UserCreate`, `UserUpdate`, `UserLogin`, `UserPasswordReset` vb.).
- Veri Doğrulama ve Dönüştürme: Şifrelerin hashlenmesi gibi özel doğrulama işlemleri `@field_validator` dekoratörü 
  ile gerçekleştirilir.
- Veritabanı Şeması: `UserInDB` sınıfı, veritabanında saklanan kullanıcı verilerini temsil eder.
- JSON Çıktı Formatlama: `UserOut` sınıfı, API çıktıları için kullanıcı verilerini formatlar.

Bu dosya, kullanıcı yönetimiyle ilgili tüm veri modelleme ve doğrulama işlemlerini merkezi bir yerde toplar ve 
uygulamanın diğer bölümleriyle uyumlu çalışmasını sağlar.
"""

from datetime import datetime, timezone
from typing import Optional, List, Annotated, Any
from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field, field_validator, BeforeValidator, model_validator

from app.core.security import get_password_hash

# ObjectId doğrulama fonksiyonu
def validate_object_id(v: Any) -> str:
    if not ObjectId.is_valid(v):
        raise ValueError("Geçersiz ObjectId")
    return str(v)

# MongoDB ObjectId doğrulaması için tür
PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    CLIENT = "client"
    SUB_CONTRACTOR = "sub_contractor"


class UserBase(BaseModel):
    """Tüm kullanıcı-ile ilgili şemaların temel sınıfı"""
    model_config = {
        "json_encoders": {ObjectId: str},
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class UserCreate(UserBase):
    """Yeni kullanıcı oluşturma şeması"""
    email: EmailStr = Field(description="Kullanıcı email adresi", examples=["user@example.com"], max_length=100)
    password: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$",
        description="En az 8 karakter, büyük/küçük harf, sayı ve özel karakter içermeli"
    )
    full_name: Optional[str] = Field(None, examples=["John Doe"], max_length=100)
    role: UserRole = Field(default=UserRole.USER)
    tenant_id: PyObjectId = Field(description="Kullanıcının bağlı olduğu tenant ID")

    @field_validator("password")
    @classmethod
    def hash_password(cls, v: str) -> str:
        """Şifreyi depolamadan önce hashleme"""
        return get_password_hash(v)


class UserUpdate(UserBase):
    """Kullanıcı bilgilerini güncelleme şeması"""
    email: Optional[EmailStr] = Field(None, examples=["user@example.com"], max_length=100)
    password: Optional[str] = Field(None, min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, examples=["John Doe"], max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = True

    @field_validator("password")
    @classmethod
    def hash_password(cls, v: Optional[str]) -> Optional[str]:
        """Eğer şifre verildiyse hashleme"""
        if v:
            return get_password_hash(v)
        return v


class UserOut(UserBase):
    """API yanıtlarında kullanıcı çıktısı için şema"""
    id: PyObjectId = Field(alias="_id")
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    # Dokümantasyon için ek örnek
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "_id": "507f1f77bcf86cd799439011",
                "email": "user@example.com",
                "full_name": "John Doe",
                "role": "user",
                "is_active": True,
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-02T00:00:00Z",
                "last_login": "2023-01-03T00:00:00Z"
            }]
        }
    }


# Geriye dönük uyumluluk için takma ad
UserResponse = UserOut


class UserInDB(UserOut):
    """Veritabanında kullanıcı saklama için genişletilmiş şema"""
    hashed_password: str = Field(description="Hashlenmiş şifre")
    email_verified: bool = False
    permissions: List[str] = Field(default_factory=list)


class UserLogin(BaseModel):
    """Kullanıcı giriş kimlik bilgileri şeması"""
    email: EmailStr = Field(examples=["user@example.com"], max_length=100)
    password: str = Field(min_length=8, max_length=100)

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "email": "user@example.com",
                "password": "Güçlü$ifre123"
            }]
        }
    }


class PasswordResetRequest(BaseModel):
    """Şifre sıfırlama talebi şeması"""
    email: EmailStr = Field(examples=["user@example.com"])

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "email": "user@example.com"
            }]
        }
    }


class PasswordChangeRequest(BaseModel):
    """Kullanıcı şifre değiştirme şeması"""
    current_password: str = Field(min_length=8, max_length=100)
    new_password: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
    )

    @model_validator(mode='after')
    def passwords_must_be_different(self) -> 'PasswordChangeRequest':
        """Yeni şifrenin mevcut şifreden farklı olduğunu doğrula"""
        if self.current_password == self.new_password:
            raise ValueError("Yeni şifre, mevcut şifreden farklı olmalıdır")
        return self


class UserPasswordReset(BaseModel):
    """Token ile şifre sıfırlama şeması"""
    new_password: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
    )
    token: str

    @field_validator("new_password")
    @classmethod
    def hash_password(cls, v: str) -> str:
        """Yeni şifreyi hashle"""
        return get_password_hash(v)