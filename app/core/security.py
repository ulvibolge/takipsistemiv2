"""
Security Module for JWT Authentication and Role-Based Access Control
--------------------------------------------------------------------
Bu dosya, FastAPI tabanlı uygulamanızda güvenlik (authentication ve authorization) işlemlerini yönetmek üzere geliştirilmiştir.

✔ JWT access ve refresh token üretimi, doğrulaması, süre kontrolü
✔ Token içeriğini decode edip kullanıcıyı veritabanından bulma
✔ Token blacklist kontrolü (logout edilmiş tokenlar reddedilir)
✔ Aktif kullanıcı kontrolü, admin rolü ve tenant ID eşlemesi
✔ Router seviyesinde yetkilendirme: izin kontrolü, admin erişimi, tenant doğrulama

Kullanılan teknolojiler:
- fastapi.security: OAuth2PasswordBearer, HTTPBearer
- jose.jwt: JWT token encode/decode
- passlib: Şifre hashleme ve doğrulama (bcrypt)
- pydantic v2: Token ve kullanıcı verisi için veri modelleme
- mongodb + motor: Kullanıcı ve token verilerini kontrol için

Her fonksiyonun kendi içinde detaylı docstring açıklamaları vardır.
Bu modül doğrudan router'lara veya servis katmanına bağlanarak kullanılabilir.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Callable, Union
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from app.core.config import settings
from app.utils.logger import logger
from app.utils.database import db_manager, COLLECTIONS
from app.core.tenant_db import get_tenant_db, get_tenant_settings
from bson import ObjectId
import logging

# Loglama
security_logger = logging.getLogger("app.security")

# Security araçları
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")
http_bearer = HTTPBearer(auto_error=False)

class TokenPayload(BaseModel):
    """JWT Token payload yapısı"""
    sub: str
    user_id: str
    tenant_id: str
    role: str
    exp: datetime
    jti: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)

class AuthenticatedUser(BaseModel):
    """Doğrulanmış kullanıcı bilgileri"""
    id: str
    email: str
    tenant_id: str
    role: str
    is_active: bool
    permissions: List[str] = Field(default_factory=list)
    full_name: Optional[str] = None
    last_login: Optional[datetime] = None
    
    # Yardımcı metodlar
    def has_permission(self, permission: str) -> bool:
        """Kullanıcının belirli bir izne sahip olup olmadığını kontrol eder"""
        return permission in self.permissions or "admin" in self.permissions
        
    def is_admin(self) -> bool:
        """Kullanıcının admin rolüne sahip olup olmadığını kontrol eder"""
        return self.role == "admin"
        
    def can_access_tenant(self, tenant_id: str) -> bool:
        """Kullanıcının belirli bir tenant'a erişip erişemeyeceğini kontrol eder"""
        return self.tenant_id == tenant_id

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Şifre doğrulama"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Şifre hashleme"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    JWT access token oluşturma
    
    Args:
        data: Token payload'ına eklenecek veriler
        expires_delta: Token geçerlilik süresi (None ise varsayılan süre kullanılır)
        
    Returns:
        str: JWT token
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    """
    Refresh token oluşturma
    
    Args:
        data: Token payload'ına eklenecek veriler
        
    Returns:
        str: JWT refresh token
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    data.update({
        "exp": expire, 
        "iat": datetime.now(timezone.utc),
        "jti": str(ObjectId()), # Unique token identifier
        "type": "refresh"  # Token tipini belirt
    })
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

async def decode_token(token: str) -> TokenPayload:
    """
    JWT token decode etme
    
    Args:
        token: JWT token
        
    Returns:
        TokenPayload: Çözümlenmiş token payload'ı
        
    Raises:
        HTTPException: Token geçersizse
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER
        )
        return TokenPayload(**payload)
    except JWTError as e:
        security_logger.error(f"Token decode error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def check_token_blacklist(token: str) -> bool:
    """
    Token'ın blacklist'te olup olmadığını kontrol eder
    
    Args:
        token: JWT token
        
    Returns:
        bool: Token blacklist'te ise True, değilse False
    """
    blacklisted = await db_manager.main_db[COLLECTIONS.TOKEN_BLACKLIST].find_one({"token": token})
    return blacklisted is not None

async def add_token_to_blacklist(token: str, user_id: str, exp_time: datetime, reason: str = "logout") -> None:
    """
    Token'ı blacklist'e ekler
    
    Args:
        token: JWT token
        user_id: Kullanıcı ID
        exp_time: Token'ın son geçerlilik zamanı
        reason: Blacklist'e ekleme nedeni (varsayılan: logout)
    """
    await db_manager.main_db[COLLECTIONS.TOKEN_BLACKLIST].insert_one({
        "token": token,
        "user_id": user_id,
        "blacklisted_at": datetime.now(timezone.utc),
        "expires_at": exp_time,
        "reason": reason
    })
    security_logger.info(f"Token blacklisted: user_id={user_id}, reason={reason}")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer)
) -> AuthenticatedUser:
    """
    Token'dan kullanıcı bilgilerini çözümleme
    
    Args:
        credentials: HTTP Authorization bilgileri
        
    Returns:
        AuthenticatedUser: Doğrulanmış kullanıcı bilgileri
        
    Raises:
        HTTPException: Yetkilendirme hatası
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yetkilendirme bilgileri eksik",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    try:
        # Token'ı decode et
        payload = await decode_token(token)

        # Token blacklist kontrolü
        if await check_token_blacklist(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token geçersiz kılınmış (oturum kapatılmış)",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Token süresi kontrolü
        if datetime.fromtimestamp(payload.exp.timestamp(), tz=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token süresi dolmuş",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Tenant veritabanını al
        tenant_db = await get_tenant_db(tenant_id=payload.tenant_id)

        # Kullanıcıyı veritabanından bul
        user = await tenant_db[COLLECTIONS.USERS].find_one({
            "_id": ObjectId(payload.user_id),
            "tenant_id": payload.tenant_id
        })

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kullanıcı bulunamadı"
            )

        # Kullanıcı aktif mi?
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kullanıcı aktif değil"
            )

        # AuthenticatedUser modeline dönüştür
        return AuthenticatedUser(
            id=str(user["_id"]),
            email=user["email"],
            tenant_id=user["tenant_id"],
            role=user["role"],
            is_active=user.get("is_active", True),
            permissions=user.get("permissions", []),
            full_name=user.get("full_name"),
            last_login=user.get("last_login")
        )
    except HTTPException:
        raise
    except Exception as e:
        security_logger.error(f"User authentication failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı doğrulanamadı"
        )

async def get_current_active_user(
    user: AuthenticatedUser = Depends(get_current_user)
) -> AuthenticatedUser:
    """
    Sadece aktif kullanıcıları döner
    
    Args:
        user: Kimliği doğrulanmış kullanıcı
        
    Returns:
        AuthenticatedUser: Aktif kullanıcı
        
    Raises:
        HTTPException: Kullanıcı aktif değilse
    """
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kullanıcı hesabı aktif değil"
        )
    return user

# Yetkilendirme helpers
async def validate_permission(
    user: AuthenticatedUser = Depends(get_current_active_user),
    required_permission: str = None
):
    """
    Kullanıcının belirli bir izne sahip olup olmadığını kontrol eder
    
    Args:
        user: Aktif kullanıcı
        required_permission: Gereken izin
        
    Raises:
        HTTPException: Kullanıcının izni yoksa
    """
    if required_permission and not user.has_permission(required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bu işlem için '{required_permission}' iznine sahip olmanız gerekiyor"
        )

async def validate_admin_role(
    user: AuthenticatedUser = Depends(get_current_active_user)
):
    """
    Kullanıcının admin rolüne sahip olup olmadığını kontrol eder
    
    Args:
        user: Aktif kullanıcı
        
    Raises:
        HTTPException: Kullanıcı admin değilse
    """
    if not user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin yetkisi gerekiyor"
        )

async def validate_tenant_access(
    user: AuthenticatedUser = Depends(get_current_active_user),
    tenant_id: str = None
):
    """
    Kullanıcının belirli bir tenant'a erişip erişemeyeceğini kontrol eder
    
    Args:
        user: Aktif kullanıcı
        tenant_id: Tenant ID
        
    Raises:
        HTTPException: Kullanıcı bu tenant'a erişemezse
    """
    if tenant_id and user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu tenant'a erişim yetkiniz yok"
        )

async def validate_admin_access(
    user: AuthenticatedUser = Depends(get_current_active_user)
):
    """
    Sadece admin erişimi kontrolü (router dependency için)
    
    Args:
        user: Aktif kullanıcı
        
    Raises:
        HTTPException: Kullanıcı admin değilse
    """
    if not user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlemi yapma yetkiniz yok (Admin gerekli)"
        )

async def validate_project_access(project_id: str, user: AuthenticatedUser = Depends(get_current_active_user)):
    """
    Kullanıcının belirli bir projeye erişim yetkisi olup olmadığını kontrol eder
    
    Args:
        project_id: Proje ID
        user: Aktif kullanıcı
        
    Raises:
        HTTPException: Kullanıcının erişim yetkisi yoksa
    """
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proje ID belirtilmemiş"
        )
        
    # Admin her projeye erişebilir
    if user.is_admin():
        return
        
    tenant_db = await get_tenant_db(tenant_id=user.tenant_id)
    
    # Proje kontrolü
    project = await tenant_db[COLLECTIONS.PROJECTS].find_one({
        "_id": ObjectId(project_id),
        "tenant_id": user.tenant_id
    })
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proje bulunamadı veya erişim yetkiniz yok"
        )
        
    # Projede görevi var mı?
    personnel_assigned = False
    if user.id in project.get("assigned_personnel", []):
        personnel_assigned = True
        
    # Proje yöneticisi mi?
    is_project_manager = False
    if user.role == "manager" and project.get("manager_id") == user.id:
        is_project_manager = True
        
    # Erişim kontrolü 
    if not (personnel_assigned or is_project_manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu projeye erişim yetkiniz yok"
        )

# Dependency Factory Fonksiyonları
def check_project_permission(permission_type: str = "read"):
    """
    Belirli bir proje işlemi için izin kontrolü yapan dependency factory
    
    Args:
        permission_type: İzin tipi (read, create, update, delete)
        
    Returns:
        Callable: Dependency fonksiyonu
    """
    required_permission = f"project_{permission_type}"
    
    async def _check_permission(
        user: AuthenticatedUser = Depends(get_current_active_user)
    ):
        # Admin her zaman tüm izinlere sahiptir
        if user.is_admin():
            return
            
        if not user.has_permission(required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu işlem için '{required_permission}' iznine sahip olmanız gerekiyor"
            )
    
    return _check_permission

async def get_token_from_request(request: Request) -> Optional[str]:
    """
    Request'ten token çıkarma
    
    Args:
        request: FastAPI request nesnesi
        
    Returns:
        Optional[str]: Token varsa döner, yoksa None
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    return None

# Örnek: Tüm işlemler için kullanılabilecek bir validator
def validate_operation_permission(operation: str):
    """
    Tenant ayarları ve kullanıcı izinlerine dayalı olarak işlem doğrulama factory'si
    
    Args:
        operation: İşlem adı (örn: "project_create", "expense_delete")
        
    Returns:
        Callable: Dependency fonksiyonu
    """
    async def _validate(
        request: Request,
        user: AuthenticatedUser = Depends(get_current_active_user)
    ):
        # Admin yetkisi tüm işlemlere erişim sağlar
        if user.is_admin():
            return
            
        # Tenant ayarlarını al
        tenant_settings, _ = await get_tenant_settings(tenant_id=user.tenant_id)
        
        # İşlem için izin kontrolü
        permission_key = f"allowed_roles_for_{operation}"
        allowed_roles = tenant_settings.get(permission_key, ["admin"])
        
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu işlemi yapma yetkiniz yok. Gereken roller: {', '.join(allowed_roles)}"
            )
            
        # İşlem için özel izin kontrolü
        if operation not in user.permissions and f"{operation}_all" not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu işlem için gerekli izne sahip değilsiniz: {operation}"
            )
    
    return _validate