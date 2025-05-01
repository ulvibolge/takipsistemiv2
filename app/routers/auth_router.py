from datetime import timedelta
from fastapi import APIRouter, Depends, status, HTTPException, Request, Body
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from app.services.auth_service import AuthService
from app.schemas.token_schema import TokenResponse, RefreshTokenRequest
from app.schemas.user_schema import UserResponse, PasswordResetRequest, PasswordChangeRequest
from pydantic import TypeAdapter
from app.core.security import get_current_user, get_current_active_user
from app.core.config import settings
from app.utils.logger import logger
from app.utils.rate_limiter import limiter
from typing import Optional

router = APIRouter(
    prefix="/auth",
    tags=["Kimlik Doğrulama"],
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Geçersiz istek"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Geçersiz bilgiler"},
        status.HTTP_403_FORBIDDEN: {"description": "Erişim reddedildi"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Çok fazla istek"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Sunucu hatası"}
    }
)

@router.post(
    "/token", 
    response_model=TokenResponse, 
    status_code=status.HTTP_200_OK,
    summary="Kullanıcı doğrulama",
    description="Kullanıcı doğrulama ve erişim ile yenileme token'ları oluşturma"
)
@limiter.limit(settings.RATE_LIMIT_AUTH_ENDPOINTS)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends()
):
    """
    Kullanıcıyı kullanıcı adı/email ve şifre ile doğrular.
    Başarılı doğrulama sonrasında erişim ve yenileme token'ları döndürür.
    
    - Üretim ortamında yenileme token'ını HTTP-only güvenli çerez olarak ayarlar
    - Brute force saldırılarını önlemek için hız sınırlaması kullanır
    """
    try:
        # Minimal KVK bilgisi ile giriş girişimini logla
        logger.info(f"Giriş denemesi: {form_data.username[:3]}***")

        tokens = await auth_service.authenticate_user(
            email=form_data.username,
            password=form_data.password
        )
        
        # Doğrulanmamış servis kullanıyorsak TypeAdapter ile yanıtı doğrula
        # tokens = TypeAdapter(TokenResponse).validate_python(tokens)

        # Üretim ortamında, yenileme token'ını HTTP-only çerez olarak ayarla
        if settings.APP_ENV == "production":
            response = JSONResponse(content=tokens.model_dump())
            response.set_cookie(
                key="refresh_token",
                value=tokens.refresh_token,
                httponly=True,
                secure=True,
                max_age=int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
                samesite="strict"
            )
            return response

        return tokens

    except HTTPException as e:
        logger.warning(f"Giriş başarısız: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Beklenmeyen giriş hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kimlik doğrulama servisi kullanılamıyor"
        )


@router.post(
    "/refresh", 
    response_model=TokenResponse, 
    status_code=status.HTTP_200_OK,
    summary="Erişim token'ı yenileme",
    description="Geçerli bir yenileme token'ı kullanarak yeni bir erişim token'ı alın"
)
@limiter.limit(settings.RATE_LIMIT_AUTH_ENDPOINTS)
async def refresh_token(
    request: Request,
    token_data: RefreshTokenRequest = Body(...),
    refresh_token_cookie: Optional[str] = None,
    auth_service: AuthService = Depends()
):
    """
    Geçerli bir yenileme token'ı kullanarak erişim token'ını yenile.
    
    Yenileme token'ı şu şekillerde sağlanabilir:
    - İstek gövdesinde
    - HTTP-only çerez olarak (üretim ortamında)
    """
    try:
        # Önce çerezden (üretim), sonra istek gövdesinden token'ı almayı dene
        token = refresh_token_cookie or token_data.refresh_token
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Yenileme token'ı gereklidir"
            )
            
        return await auth_service.refresh_access_token(token)
        
    except HTTPException as e:
        logger.warning(f"Token yenileme başarısız: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Token yenileme hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token yenilenemedi"
        )


@router.get(
    "/me", 
    response_model=UserResponse,
    summary="Mevcut kullanıcıyı getir",
    description="Şu anda kimliği doğrulanmış kullanıcı hakkında bilgi al"
)
async def get_current_user_info(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Şu anda kimliği doğrulanmış kullanıcı hakkında bilgi döndürür.
    Geçerli bir erişim token'ı gerektirir.
    """
    return current_user


@router.post(
    "/logout", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Kullanıcı çıkışı",
    description="Mevcut kullanıcının yenileme token'ını geçersiz kıl"
)
async def logout(
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends()
):
    """
    Şu işlemleri yaparak mevcut kullanıcının çıkışını sağlar:
    - Veritabanındaki yenileme token'ını iptal eder
    - Yenileme token çerezini temizler (üretim ortamında)
    """
    try:
        await auth_service.revoke_refresh_token(current_user["id"])

        if settings.APP_ENV == "production":
            response = JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
            response.delete_cookie(key="refresh_token")
            return response

        return None

    except Exception as e:
        logger.error(f"Çıkış hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Çıkış işlemi yapılamadı"
        )

@router.post(
    "/password/reset-request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Şifre sıfırlama isteği",
    description="Kullanıcının e-postasına bir sıfırlama bağlantısı göndererek şifre sıfırlama sürecini başlat"
)
@limiter.limit(settings.RATE_LIMIT_AUTH_ENDPOINTS)
async def request_password_reset(
    request: Request,
    data: PasswordResetRequest = Body(...),
    auth_service: AuthService = Depends()
):
    """
    Şifre sıfırlama sürecini başlatır:
    1. Tek kullanımlık sıfırlama token'ı oluşturur
    2. Sıfırlama talimatlarıyla bir e-posta gönderir
    
    E-posta mevcut olmasa bile her zaman 202 Accepted döndürür
    (kullanıcı numaralandırmasını önlemek için)
    """
    try:
        # E-posta mevcut olmasa bile her zaman 202 döndür (güvenlik)
        await auth_service.request_password_reset(email=data.email)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "E-posta mevcutsa şifre sıfırlama talimatları gönderildi"}
        )
    except Exception as e:
        logger.error(f"Şifre sıfırlama isteği hatası: {str(e)}", exc_info=True)
        # Kullanıcı numaralandırmasını önlemek için yine de 202 döndür
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "E-posta mevcutsa şifre sıfırlama talimatları gönderildi"}
        )

@router.post(
    "/password/change",
    status_code=status.HTTP_200_OK,
    summary="Şifre değiştir",
    description="Kimliği doğrulanmış kullanıcının şifresini değiştir"
)
async def change_password(
    data: PasswordChangeRequest = Body(...),
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends()
):
    """
    Kimliği doğrulanmış kullanıcının şifresini değiştirir.
    
    Gereksinimler:
    - Mevcut şifre doğrulaması
    - Geçerli erişim token'ı
    """
    try:
        await auth_service.change_password(
            user_id=current_user["id"],
            current_password=data.current_password,
            new_password=data.new_password
        )
        
        return {"message": "Şifre başarıyla değiştirildi"}
        
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Şifre değiştirme hatası: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Şifre değiştirilemedi"
        )