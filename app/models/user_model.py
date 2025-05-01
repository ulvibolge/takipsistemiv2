"""
Bu dosya, MongoDB üzerinde kullanıcı belgelerinin yapısını tanımlar.

- `hashed_password`, veritabanında saklanan şifreyi içerir.
- `email_verified`, kullanıcının e-posta doğrulama durumu
- `permissions`, özel erişim izinleri içerir
"""

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId
from enum import Enum


class PyObjectId(str):
    """MongoDB ObjectId doğrulayıcı"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    CLIENT = "client"
    SUB_CONTRACTOR = "sub_contractor"


class User(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    hashed_password: str
    email_verified: bool = False
    permissions: List[str] = Field(default_factory=list)
    tenant_id: PyObjectId
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: str
        }
