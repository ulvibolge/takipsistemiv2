from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from enum import Enum
from app.core.config import settings


class TokenType(str, Enum):
    """Token türleri"""
    BEARER = "bearer"
    MAC = "mac"
    JWT = "jwt"


class TokenBase(BaseModel):
    """Tüm token modelleri için temel şema"""
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_expires_in": 86400
            }
        }


class TokenResponse(TokenBase):
    """
    Access ve refresh token yanıtı için şema
    """
    access_token: str = Field(
        ...,
        example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        min_length=100,
        description="JWT formatında access token"
    )
    refresh_token: str = Field(
        ...,
        example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        min_length=100,
        description="JWT formatında refresh token"
    )
    token_type: TokenType = Field(
        TokenType.BEARER,
        description="Token tipi (default: bearer)"
    )
    expires_in: int = Field(
        default=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        example=3600,
        description="Access token geçerlilik süresi (saniye)"
    )
    refresh_expires_in: int = Field(
        default=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        example=86400,
        description="Refresh token geçerlilik süresi (saniye)"
    )
    scope: Optional[str] = Field(
        None,
        example="read write admin",
        description="Yetki kapsamı (opsiyonel)"
    )

    @field_validator('access_token', 'refresh_token')
    @classmethod
    def validate_jwt_format(cls, v: str) -> str:
        """
        Basit JWT format kontrolü
        """
        if not v.startswith("eyJ") or len(v.split('.')) != 3:
            raise ValueError("Geçersiz JWT formatı")
        return v


class RefreshTokenRequest(TokenBase):
    """
    Refresh token isteği için şema
    """
    refresh_token: str = Field(
        ...,
        example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        min_length=100,
        description="Geçerli refresh token"
    )
    grant_type: str = Field(
        "refresh_token",
        pattern="^refresh_token$",
        description="OAuth2 grant type"
    )


class TokenPayload(BaseModel):
    """
    JWT token içinde gönderilen payload alanları
    """
    sub: str = Field(..., description="Kullanıcı identifier (email/id)")
    user_id: str = Field(..., description="Kullanıcı unique ID")
    tenant_id: str = Field(..., description="Tenant/organizasyon ID")
    role: str = Field(..., description="Kullanıcı rolü")
    exp: int = Field(..., description="Son kullanma tarihi (timestamp)")
    iat: int = Field(..., description="Oluşturulma tarihi (timestamp)")
    jti: Optional[str] = Field(None, description="Token unique identifier")
    scopes: Optional[List[str]] = Field(
        None,
        description="Yetki listesi (opsiyonel)"
    )


class TokenBlacklist(TokenBase):
    """
    Geçersiz kılınan token'lar için şema
    """
    token: str = Field(..., description="Geçersiz token değeri")
    user_id: str = Field(..., description="İlgili kullanıcı ID")
    invalidated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Geçersiz kılınma tarihi"
    )
    reason: Optional[str] = Field(
        None,
        description="Geçersiz kılma nedeni (logout, compromise vb.)"
    )
    expires_at: datetime = Field(
        ...,
        description="Token'ın orijinal son kullanma tarihi"
    )


class TokenAuditLog(TokenBase):
    """
    Token işlemleri için audit log şeması
    """
    user_id: str = Field(..., description="İlgili kullanıcı ID")
    action: str = Field(
        ...,
        pattern="^(login|refresh|logout|revoke)$",
        description="İşlem türü"
    )
    ip_address: str = Field(
        ...,
        example="192.168.1.1",
        description="İşlem IP adresi"
    )
    user_agent: str = Field(
        ...,
        example="Mozilla/5.0",
        description="Kullanıcı agent bilgisi"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="İşlem zamanı"
    )
    device_id: Optional[str] = Field(
        None,
        description="Cihaz ID (opsiyonel)"
    )
    location: Optional[str] = Field(
        None,
        description="Konum bilgisi (opsiyonel)"
    )
