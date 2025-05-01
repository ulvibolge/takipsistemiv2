"""
Bu dosya, uygulama genelinde kullanılan ortak FastAPI dependency fonksiyonlarını içerir.
Aşağıdaki görevleri yerine getirir:

- JWT token üzerinden kimlik doğrulaması yapar ve geçerli kullanıcıyı elde eder.
- Kullanıcının sistemde aktif olup olmadığını ve erişim yetkisini kontrol eder.
- `get_current_active_user`, `get_current_admin_user` gibi fonksiyonlar, ilgili route'lardaki güvenliği sağlar.

Geliştirici Notu:
Bu dosya, `auth_service` üzerinden kullanıcı doğrulaması yapar.
Tüm API uç noktalarında tekrar eden kimlik doğrulama işlemlerinin merkezi olarak yönetilmesini sağlar.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timezone
from app.schemas.token_schema import TokenPayload
from app.services.auth_service import AuthService
from app.models.user_model import User
from app.core.config import settings
datetime.now(timezone.utc)  # UTC zaman dilimini kullanmak için
# Token ile kimlik doğrulama için OAuth2 bearer scheme
reuseable_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")

def get_current_user(token: str = Depends(reuseable_oauth2)) -> User:
    """JWT token'i decode edip kullanıcıyı doğrular."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_data = TokenPayload(**payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geçersiz kimlik doğrulama bilgisi"
        )

    user = AuthService.get_user_by_id(token_data.user_id, token_data.tenant_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı"
        )
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Aktif kullanıcı kontrolü yapar."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Kullanıcı pasif durumda")
    return current_user

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Yalnızca admin kullanıcılar için erişim kontrolü sağlar."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Yalnızca yöneticiler erişebilir")
    return current_user
