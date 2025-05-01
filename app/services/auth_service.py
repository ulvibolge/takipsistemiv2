"""
auth_service.py

Bu dosya, kimlik doğrulama işlemlerini yöneten bir servis sınıfı içerir. 
Geliştiriciler için temel işlevler:
1. Kullanıcıyı e-posta ve şifre ile doğrulama.
2. JWT access ve refresh token üretimi.
3. Refresh token kullanarak yeni access token oluşturma.
4. Refresh token'ı geçersiz kılma (logout işlemi).

Bu sınıf, FastAPI uygulamalarında kimlik doğrulama ve yetkilendirme süreçlerini kolaylaştırmak için tasarlanmıştır.
"""

# app/services/auth_service.py Ana Görevleri:
#1.	Kullanıcıyı email ve şifreyle doğrulamak
#2.	Access & refresh token üretmek (firma_id, rol vb. payload'larla)
#3.	Refresh token’ı doğrulayıp yeni access token üretmek
#4.	Refresh token'ı geçersiz kılmak (çıkış işlemi)


from datetime import timedelta, datetime,timezone
from fastapi import  HTTPException, status
from jose import jwt, JWTError
from passlib.context import CryptContext
from bson import ObjectId

from app.utils.database import db_manager, COLLECTIONS
from app.core.config import settings
from app.schemas.token_schema import TokenResponse
#from app.schemas.token import RefreshTokenRequest
from app.schemas.user_schema import UserInDB
from app.utils.logger import logger

datetime.now(timezone.utc)

class AuthService:
    """
    Kimlik doğrulama işlemlerini yöneten servis sınıfı.

    Görevleri:
    - Kullanıcı e-posta ve şifresini doğrulama
    - JWT access ve refresh token üretimi
    - Refresh token'a göre access token yenileme
    - Refresh token geçersiz kılma (logout)

    Kullanım:
    - FastAPI route'larında Depends(AuthService) ile çağrılabilir.
    - JWT payload'larında kullanıcı bilgisi, tenant_id ve rol içerir.
    """
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS

    async def authenticate_user(self, email: str, password: str) -> TokenResponse:
        """
        E-posta ve şifreyle kullanıcıyı doğrular, JWT ve refresh token üretir.
        """
        user_data = await db_manager.main_db[COLLECTIONS.USERS].find_one({"email": email})
        if not user_data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kullanıcı bulunamadı")

        user = UserInDB(**user_data)

        if not self.pwd_context.verify(password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Hatalı şifre")

        access_token = self._create_access_token(data={
            "sub": user.email,
            "user_id": str(user.id),
            "tenant_id": user.tenant_id,
            "role": user.role
        })

        refresh_token = self._create_refresh_token(data={
            "sub": user.email,
            "user_id": str(user.id)
        })

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )

    def _create_access_token(self, data: dict) -> str:
        """
        JWT access token üretir.
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def _create_refresh_token(self, data: dict) -> str:
        """
        Refresh token üretir.
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """
        Verilen refresh token'a göre yeni access token üretir.
        """
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=[self.algorithm])
            email = payload.get("sub")
            user_id = payload.get("user_id")
            if not email or not user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Geçersiz token")

            user_data = await db_manager.main_db[COLLECTIONS.USERS].find_one({"_id": ObjectId(user_id)})
            if not user_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

            user = UserInDB(**user_data)

            return TokenResponse(
                access_token=self._create_access_token(data={
                    "sub": user.email,
                    "user_id": str(user.id),
                    "tenant_id": user.tenant_id,
                    "role": user.role
                }),
                refresh_token=refresh_token,
                token_type="bearer"
            )

        except JWTError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token doğrulanamadı")

    async def revoke_refresh_token(self, user_id: str) -> None:
        """
        Refresh token'ı geçersiz kılma işlemi (örneğin logout).
        Basit projelerde boş bırakılabilir, büyük sistemlerde blacklist DB gerekebilir.
        """
        logger.info(f"Kullanıcı {user_id} çıkış yaptı, refresh token devre dışı bırakıldı (simüle edildi).")
        pass  # İsteğe bağlı: refresh token blacklist sistemine entegre edilebilir
