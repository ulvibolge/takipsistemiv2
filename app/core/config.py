"""
Config Module for FastAPI Application
-------------------------------------
Bu dosya, Takip Sistemi yazılımı için ortam değişkenlerinin ve uygulama ayarlarının 
merkezi olarak tanımlandığı Pydantic v2 tabanlı yapılandırma modülüdür.

✅ .env dosyasından ayarları okur (ortama göre .env.development, .env.production vs.)
✅ MongoDB, JWT, Uvicorn, Redis, RabbitMQ, CORS, statik dizin ve loglama gibi tüm yapılandırmaları içerir
✅ Settings sınıfı BaseSettings'den türemiştir ve tip güvenli bir şekilde veri doğrulama sağlar
✅ Pydantic V2 ile uyumlu `SettingsConfigDict` yapısı kullanılmıştır
✅ Ortam değişkenlerine alias tanımlanarak .env dosyasından isim eşleşmesi yapılır
✅ Uygulama ayağa kalkarken `settings = Settings()` çağrısıyla bu yapı devreye girer

Güvenlik için üretim ortamında otomatik doğrulamalar yapılır:
- DEBUG kapalı mı?
- SECRET_KEY yeterince uzun mu?
- API dokümantasyonu devre dışı mı?
- Özel JWT secret oluşturulmuş mu?

Bu modül, farklı ortamlar (dev, test, prod) için tutarlı ve tip güvenli bir yapılandırma sağlar.
"""
import os
import json
import socket
import secrets
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Union, Annotated
from datetime import timedelta
from functools import lru_cache
from pydantic import (
    Field, 
    field_validator, 
    ValidationError, 
    computed_field,
    model_validator,
    HttpUrl,
    SecretStr
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ortam değişkeni kontrol fonksiyonu
def get_environment() -> str:
    """Çalışma ortamını belirler, varsayılan olarak 'development'"""
    return os.getenv("APP_ENV", "development").lower()

class LoggingSettings(BaseSettings):
    """Loglama ayarları alt modeli"""
    LOG_LEVEL: str = Field("INFO", alias="LOG_LEVEL")
    LOG_FILE: Path = Field("./logs/app.log", alias="LOG_FILE")
    LOG_ROTATION: str = Field("10MB", alias="LOG_ROTATION")
    LOG_RETENTION: int = Field(30, alias="LOG_RETENTION")  # Gün sayısı
    LOG_FORMAT: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
        alias="LOG_FORMAT"
    )
    LOG_TO_CONSOLE: bool = Field(True, alias="LOG_TO_CONSOLE")
    LOG_TO_FILE: bool = Field(True, alias="LOG_TO_FILE")
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Geçersiz log seviyesi. Geçerli değerler: {valid_levels}")
        return v.upper()

class DatabaseSettings(BaseSettings):
    """Veritabanı ayarları alt modeli"""
    MONGO_URI: str = Field("mongodb://localhost:27017", alias="MONGO_URI")
    MONGO_DB_NAME: str = Field("takip_db", alias="MONGO_DB_NAME")
    MONGO_MAX_POOL_SIZE: int = Field(20, alias="MONGO_MAX_POOL_SIZE")
    MONGO_USER: str = Field("takip_user", alias="MONGO_USER")
    MONGO_PASSWORD: str = Field("StrongPass123!", alias="MONGO_PASSWORD")
    MONGO_TIMEOUT_MS: int = Field(30000, alias="MONGO_TIMEOUT_MS")
    MONGO_RETRY_WRITES: bool = Field(True, alias="MONGO_RETRY_WRITES")
    MONGO_INIT_TIMEOUT: int = Field(30000, alias="MONGO_INITDB_TRANSACTION_TIMEOUT")
    MONGO_MAX_RETRIES: int = Field(5, alias="MONGO_INITDB_MAX_RETRIES")
    
    @computed_field
    def connection_string(self) -> str:
        """MongoDB bağlantı stringini döndürür"""
        if not self.MONGO_URI:
            return f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}@localhost:27017/{self.MONGO_DB_NAME}"
        
        # Eğer URI verilmişse, kullanıcı adı ve şifreyi URI'ye ekle
        uri_str = str(self.MONGO_URI)
        if "mongodb://" in uri_str and "@" not in uri_str:
            # Kullanıcı adı ve şifre ekle
            parts = uri_str.split("://", 1)
            auth_part = f"{self.MONGO_USER}:{self.MONGO_PASSWORD}@"
            return f"{parts[0]}://{auth_part}{parts[1]}"
            
        return uri_str

class JWTSettings(BaseSettings):
    """JWT ve kimlik doğrulama ayarları alt modeli"""
    SECRET_KEY: str = Field("default_secret_change_in_production", min_length=32, alias="SECRET_KEY")
    ALGORITHM: str = Field("HS256", alias="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, gt=0, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(30, gt=0, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    JWT_ISSUER: str = Field("TakipSistemi", alias="JWT_ISSUER")
    JWT_AUDIENCE: str = Field("TakipSistemiUsers", alias="JWT_AUDIENCE")
    JWT_TOKEN_PREFIX: str = Field("Bearer", alias="JWT_TOKEN_PREFIX")
    JWT_BLACKLIST_ENABLED: bool = Field(True, alias="JWT_BLACKLIST_ENABLED")
    JWT_BLACKLIST_TOKEN_CHECKS: Set[str] = Field(
        default_factory=lambda: {"access", "refresh"},
        alias="JWT_BLACKLIST_TOKEN_CHECKS"
    )
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = Field(24, alias="PASSWORD_RESET_TOKEN_EXPIRE_HOURS")
    
    @field_validator("ALGORITHM")
    @classmethod
    def validate_algorithm(cls, v):
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(f"Desteklenmeyen algoritma. Kullanılabilir: {', '.join(allowed)}")
        return v
    
    @model_validator(mode='after')
    def check_and_generate_secret_key(self):
        """Üretim ortamında rastgele bir SECRET_KEY oluşturur (eğer varsayılan değer kullanılmışsa)"""
        if self.SECRET_KEY == "default_secret_change_in_production":
            # Üretim ortamında varsayılan anahtar kullanmayı engelle
            if get_environment() == "production":
                raise ValueError(
                    "Üretim ortamında varsayılan SECRET_KEY kullanılamaz. "
                    "Lütfen güçlü bir SECRET_KEY belirtin."
                )
            # Geliştirme ortamında otomatik olarak güçlü bir anahtar oluştur
            self.SECRET_KEY = secrets.token_urlsafe(64)
        return self
    
    @computed_field
    def access_token_expires(self) -> timedelta:
        """Access token geçerlilik süresini döndürür"""
        return timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    @computed_field
    def refresh_token_expires(self) -> timedelta:
        """Refresh token geçerlilik süresini döndürür"""
        return timedelta(days=self.REFRESH_TOKEN_EXPIRE_DAYS)

class CORSSettings(BaseSettings):
    """CORS ayarları alt modeli"""
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")
    CORS_ALLOW_CREDENTIALS: bool = Field(True, alias="CORS_ALLOW_CREDENTIALS")
    CORS_ALLOW_METHODS: List[str] = Field(
        default_factory=lambda: ["*"],
        alias="CORS_ALLOW_METHODS"
    )
    CORS_ALLOW_HEADERS: List[str] = Field(
        default_factory=lambda: ["*"],
        alias="CORS_ALLOW_HEADERS"
    )
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if not v:
            return ["*"]
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v if isinstance(v, list) else ["*"]

class SecuritySettings(BaseSettings):
    """Güvenlik ve şifre politikası ayarları"""
    CSRF_PROTECTION: bool = Field(False, alias="CSRF_PROTECTION")
    BCRYPT_LOG_ROUNDS: int = Field(12, alias="BCRYPT_LOG_ROUNDS")
    MIN_PASSWORD_LENGTH: int = Field(8, alias="MIN_PASSWORD_LENGTH")
    REQUIRE_PASSWORD_UPPERCASE: bool = Field(True, alias="REQUIRE_PASSWORD_UPPERCASE")
    REQUIRE_PASSWORD_LOWERCASE: bool = Field(True, alias="REQUIRE_PASSWORD_LOWERCASE")
    REQUIRE_PASSWORD_DIGITS: bool = Field(True, alias="REQUIRE_PASSWORD_DIGITS")
    REQUIRE_PASSWORD_SPECIAL: bool = Field(True, alias="REQUIRE_PASSWORD_SPECIAL")
    PASSWORD_EXPIRY_DAYS: int = Field(90, alias="PASSWORD_EXPIRY_DAYS")
    MAX_FAILED_LOGIN_ATTEMPTS: int = Field(5, alias="MAX_FAILED_LOGIN_ATTEMPTS")
    ACCOUNT_LOCKOUT_MINUTES: int = Field(30, alias="ACCOUNT_LOCKOUT_MINUTES")
    
    @model_validator(mode='after')
    def validate_security_settings(self):
        """Güvenlik ayarlarının tutarlılığını kontrol eder"""
        # Şifre uzunluğu en az 8 olmalı
        if self.MIN_PASSWORD_LENGTH < 8:
            self.MIN_PASSWORD_LENGTH = 8
            
        # Üretim ortamında CSRF koruması etkin olmalı
        if get_environment() == "production" and not self.CSRF_PROTECTION:
            logging.warning(
                "Üretim ortamında CSRF koruması devre dışı. "
                "Güvenlik için CSRF_PROTECTION=True yapmanız önerilir."
            )
        return self

class RateLimitSettings(BaseSettings):
    """Hız sınırlama ayarları"""
    RATE_LIMIT_ENABLED: bool = Field(True, alias="RATE_LIMIT_ENABLED")
    RATE_LIMIT_PER_MINUTE: int = Field(60, alias="RATE_LIMIT_PER_MINUTE")
    RATE_LIMIT_BURST: int = Field(120, alias="RATE_LIMIT_BURST")
    RATE_LIMIT_BACKEND: str = Field("memory", alias="RATE_LIMIT_BACKEND")
    RATE_LIMIT_STRATEGY: str = Field("fixed-window", alias="RATE_LIMIT_STRATEGY")
    RATE_LIMIT_WHITELIST_IPS: List[str] = Field(
        default_factory=list,
        alias="RATE_LIMIT_WHITELIST_IPS"
    )

class NotificationSettings(BaseSettings):
    """Bildirim ayarları"""
    SMTP_SERVER: str = Field("smtp.gmail.com", alias="SMTP_SERVER")
    SMTP_PORT: int = Field(587, alias="SMTP_PORT")
    SMTP_USERNAME: Optional[str] = Field(None, alias="SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = Field(None, alias="SMTP_PASSWORD")
    EMAIL_FROM: Optional[str] = Field(None, alias="EMAIL_FROM")
    EMAIL_FROM_NAME: str = Field("Takip Sistemi", alias="EMAIL_FROM_NAME")
    EMAIL_ENABLED: bool = Field(False, alias="EMAIL_ENABLED")
    
    @model_validator(mode='after')
    def validate_email_settings(self):
        """E-posta ayarlarının tutarlılığını kontrol eder"""
        if self.EMAIL_ENABLED:
            if not self.SMTP_USERNAME or not self.SMTP_PASSWORD or not self.EMAIL_FROM:
                raise ValueError(
                    "E-posta gönderimi etkinleştirildi, ancak gerekli SMTP ayarları eksik. "
                    "SMTP_USERNAME, SMTP_PASSWORD ve EMAIL_FROM değerlerini kontrol edin."
                )
        return self

class Settings(BaseSettings):
    """Ana yapılandırma sınıfı - tüm alt modelleri birleştirir"""
    # Uygulama Temel Ayarları
    APP_NAME: str = Field("TakipSistemi", alias="APP_NAME")
    APP_ENV: str = Field("development", alias="APP_ENV")
    DEBUG: bool = Field(False, alias="DEBUG")
    DOCKERIZED: bool = Field(False, alias="DOCKERIZED")
    STATIC_FILES_DIR: Path = Field("./static", alias="STATIC_FILES_DIR")
    TEMPLATES_DIR: Path = Field("./templates", alias="TEMPLATES_DIR")
    UPLOADS_DIR: Path = Field("./uploads", alias="UPLOADS_DIR")
    MAX_UPLOAD_SIZE_MB: int = Field(10, alias="MAX_UPLOAD_SIZE_MB")
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = Field(
        default_factory=lambda: [".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".docx"],
        alias="ALLOWED_UPLOAD_EXTENSIONS"
    )
    
    # API Ayarları
    API_PREFIX: str = Field("/api/v1", alias="API_PREFIX")
    DOCS_URL: Optional[str] = Field("/docs", alias="DOCS_URL")
    REDOC_URL: Optional[str] = Field("/redoc", alias="REDOC_URL")
    OPENAPI_URL: Optional[str] = Field("/openapi.json", alias="OPENAPI_URL")
    
    # Sunucu (Uvicorn) Ayarları
    UVICORN_HOST: str = Field("0.0.0.0", alias="UVICORN_HOST")
    UVICORN_PORT: int = Field(8000, alias="UVICORN_PORT")
    UVICORN_WORKERS: int = Field(1, alias="UVICORN_WORKERS")
    UVICORN_RELOAD: bool = Field(True, alias="UVICORN_RELOAD")
    
    # Önbellek Ayarları
    REDIS_HOST: str = Field("127.0.0.1", alias="REDIS_HOST")
    REDIS_PORT: int = Field(6379, alias="REDIS_PORT")
    REDIS_DB: int = Field(0, alias="REDIS_DB")
    REDIS_PASSWORD: Optional[str] = Field(None, alias="REDIS_PASSWORD")
    CACHE_TTL_SECONDS: int = Field(600, alias="CACHE_TTL_SECONDS")  # 10 dakika
    
    # Alt Model Entegrasyonları
    logging: LoggingSettings = LoggingSettings()
    db: DatabaseSettings = DatabaseSettings()
    jwt: JWTSettings = JWTSettings()
    cors: CORSSettings = CORSSettings()
    security: SecuritySettings = SecuritySettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    notification: NotificationSettings = NotificationSettings()
    
    # RabbitMQ Ayarları
    RABBITMQ_HOST: str = Field("localhost", alias="RABBITMQ_HOST")
    RABBITMQ_PORT: int = Field(5672, alias="RABBITMQ_PORT")
    RABBITMQ_USER: str = Field("guest", alias="RABBITMQ_USER")
    RABBITMQ_PASSWORD: str = Field("guest", alias="RABBITMQ_PASSWORD")
    RABBITMQ_VHOST: str = Field("/", alias="RABBITMQ_VHOST")
    
    # Tenant Ayarları
    DEFAULT_TENANT_DB_PREFIX: str = Field("tenant_", alias="DEFAULT_TENANT_DB_PREFIX")
    TENANT_CACHE_TTL_SECONDS: int = Field(600, alias="TENANT_CACHE_TTL_SECONDS")
    TENANT_CACHE_MAX_SIZE: int = Field(100, alias="TENANT_CACHE_MAX_SIZE")
    
    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v):
        allowed = {"development", "testing", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"Geçersiz ortam. Kullanılabilir: {', '.join(allowed)}")
        return v
    
    @computed_field
    def hostname(self) -> str:
        """Sunucu adını döndürür"""
        return socket.gethostname()
    
    @computed_field
    def is_production(self) -> bool:
        """Üretim ortamında çalışıp çalışmadığını belirtir"""
        return self.APP_ENV == "production"
    
    @computed_field
    def max_upload_size_bytes(self) -> int:
        """Maksimum dosya yükleme boyutunu byte cinsinden döndürür"""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    
    model_config = SettingsConfigDict(
        env_file=f".env.{get_environment()}",
        env_file_encoding="utf-8",
        case_sensitive=True,
        secrets_dir="/run/secrets",
        extra="ignore",
        validate_default=True,
    )
    
    def __init__(self, **data):
        super().__init__(**data)
        
        # Dizinlerin varlığını kontrol et ve yoksa oluştur
        for directory in [self.STATIC_FILES_DIR, self.TEMPLATES_DIR, self.UPLOADS_DIR]:
            os.makedirs(directory, exist_ok=True)
        
        # Log dizinini oluştur
        log_dir = os.path.dirname(self.logging.LOG_FILE)
        os.makedirs(log_dir, exist_ok=True)

@lru_cache()
def get_settings() -> Settings:
    """
    Ayarları döndürür (önbelleğe alınmış).
    Bu fonksiyon, ayarların birden çok kez yüklenmesini önler.
    
    Returns:
        Settings: Yapılandırma nesnesi
    """
    try:
        return Settings()
    except ValidationError as e:
        print(f"⛔ Ayarlar yüklenirken hata oluştu: {e}")
        raise

# Ayarları başlat
try:
    settings = get_settings()
    
    # Üretim ortamı kontrolleri
    if settings.is_production:
        assert not settings.DEBUG, "⛔ Üretim ortamında DEBUG modu kapalı olmalı"
        assert len(settings.jwt.SECRET_KEY) >= 64, "⛔ Üretimde SECRET_KEY en az 64 karakter olmalı"
        assert settings.DOCS_URL is None, "⛔ Üretimde API dokümantasyonu kapatılmalı (DOCS_URL=None)"
        assert settings.OPENAPI_URL is None, "⛔ Üretimde OpenAPI şeması kapatılmalı (OPENAPI_URL=None)"
        assert settings.security.CSRF_PROTECTION, "⛔ Üretimde CSRF koruması açık olmalı"
        
except ValidationError as e:
    print(f"⛔ Ayarlar doğrulanırken kritik hatalar tespit edildi: {e}")
    raise
except AssertionError as e:
    print(f"⛔ Üretim ortamı güvenlik kontrollerinde hata: {e}")
    raise
except Exception as e:
    print(f"⛔ Beklenmeyen hata: {e}")
    raise