"""
Bu dosya, FastAPI bağımlılık sistemi ile kullanıcı kimlik doğrulama ve yetki kontrol işlemlerini yürütür.

✅ Özellikler:
- JWT token çözümleme
- Tenant tabanlı kullanıcı doğrulama
- Aktif kullanıcı ve admin kullanıcı kontrolleri

Kullanım:
- `resolve_authenticated_user`: Giriş yapmış kullanıcıyı getirir
- `resolve_active_user`: Sadece aktif kullanıcıları kabul eder
- `resolve_admin_user`: Sadece admin yetkili kullanıcıları kabul eder
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from bson import ObjectId

from app.core.config import settings
from app.utils.database import db_manager, COLLECTIONS
from app.models.user_model import User

# Token çözümleyici
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def resolve_authenticated_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    JWT token'ı çözerek tenant bazlı kullanıcıyı veritabanından getirir.
    """
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Geçersiz kimlik doğrulama bilgisi",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")

        if not user_id or not tenant_id:
            raise auth_error

    except JWTError:
        raise auth_error

    async with db_manager.get_tenant_db(tenant_id) as db:
        user_data = await db[COLLECTIONS.USERS].find_one({"_id": ObjectId(user_id)})

        if not user_data:
            raise auth_error

        return User(**user_data)


async def resolve_active_user(
    user: User = Depends(resolve_authenticated_user)
) -> User:
    """
    Sadece aktif kullanıcıları döner.
    """
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Kullanıcı pasif durumda")
    return user


async def resolve_admin_user(
    user: User = Depends(resolve_authenticated_user)
) -> User:
    """
    Sadece admin rolüne sahip kullanıcıları döner.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Yetersiz yetki: sadece admin")
    return user
