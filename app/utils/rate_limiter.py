"""
Rate Limiter modülü, API isteklerini sınırlamak ve DDoS saldırılarına karşı koruma sağlamak için kullanılır.
Bu modül aşağıdaki özellikleri sağlar:

- Esnek Rate Limit Yapılandırması: Endpoint bazlı limit tanımlama
- Kullanıcı veya IP Bazlı Sınırlama: Kimlik doğrulaması yapılmış kullanıcılar veya IP adresi bazlı sınırlama
- Veritabanı Entegrasyonu: Limit konfigürasyonlarını veritabanından dinamik olarak alma
- Decorator ve Middleware Desteği: Farklı kullanım senaryoları için esneklik

Bu modül, yüksek trafik durumlarında API'nin stabil kalmasını ve kaynakların adil dağıtılmasını sağlar.
"""

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional, Callable, Any
import asyncio
import functools
from app.core.config import settings
from app.utils.logger import logger
from app.utils.database import db_manager, COLLECTIONS
from bson import ObjectId
from jose import jwt, JWTError

# UTC timezone'ı için global değişken
UTC_TZ = timezone.utc

class RateLimiter:
    """
    API isteklerini sınırlamak için kullanılan sınıf.
    In-memory veya veritabanı destekli rate limiting uygular.
    """
    def __init__(self):
        # Aktif istek sayaçları: {identifier: (count, last_request_time)}
        self.rate_limit_storage: Dict[str, Tuple[int, datetime]] = {}
        
        # Thread-safe operasyonlar için asyncio lock
        self.lock = asyncio.Lock()
        
        # Endpoint bazlı limit konfigürasyonları için önbellek
        self.rate_limit_cache: Dict[str, Tuple[int, int]] = {}

    async def _get_rate_limit_config(self, endpoint: str) -> Tuple[int, int]:
        """
        Endpoint'e özel rate limit konfigürasyonu getirir.
        
        Args:
            endpoint: İstek yapılan endpoint yolu
            
        Returns:
            Tuple[int, int]: (izin_verilen_istek_sayısı, saniye_cinsinden_süre)
        """
        # Önbellekte varsa doğrudan döndür
        if endpoint in self.rate_limit_cache:
            return self.rate_limit_cache[endpoint]

        # Veritabanından endpoint konfigürasyonunu sorgula
        config = await db_manager.main_db[COLLECTIONS.RATE_LIMITS].find_one(
            {"endpoint": endpoint}
        )
        
        if config:
            limits = (config["requests"], config["per_seconds"])
            # Sonucu önbelleğe al
            self.rate_limit_cache[endpoint] = limits
            return limits
        
        # Varsayılan limitler
        default_limits = (
            settings.DEFAULT_RATE_LIMIT_REQUESTS,
            settings.DEFAULT_RATE_LIMIT_SECONDS
        )
        # Varsayılan limitleri önbelleğe al
        self.rate_limit_cache[endpoint] = default_limits
        return default_limits

    async def check_rate_limit(self, request: Request, user_id: Optional[str] = None, requests: Optional[int] = None, per_seconds: Optional[int] = None):
        """
        Rate limit kontrolü yapar ve limit aşılmışsa hata fırlatır.
        
        Args:
            request: FastAPI istek nesnesi
            user_id: Kimliği doğrulanmış kullanıcı ID'si (varsa)
            requests: İsteğe bağlı özel limit (veritabanı sorgusu yerine)
            per_seconds: İsteğe bağlı özel süre (veritabanı sorgusu yerine)
            
        Raises:
            HTTPException: Rate limit aşıldığında 429 hatası
        """
        endpoint = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        
        # Kullanıcı ID varsa onu, yoksa IP adresini tanımlayıcı olarak kullan
        identifier = f"{endpoint}:{user_id}" if user_id else f"{endpoint}:{client_ip}"

        # Özel limit belirtildiyse doğrudan kullan, yoksa veritabanından al
        if requests is not None and per_seconds is not None:
            max_requests, per_seconds = requests, per_seconds
        else:
            # Rate limit konfigürasyonunu al
            max_requests, per_seconds = await self._get_rate_limit_config(endpoint)

        # Thread-safe işlem için lock kullan
        async with self.lock:
            current_time = datetime.now(UTC_TZ)
            # Mevcut istek sayısı ve son istek zamanını al veya varsayılan değer kullan
            request_count, last_request = self.rate_limit_storage.get(identifier, (0, current_time))

            # Süre dolmuşsa sayacı sıfırla
            time_diff = (current_time - last_request).total_seconds()
            if time_diff > per_seconds:
                request_count = 0
                last_request = current_time

            # Rate limit kontrolü - limit aşıldıysa hata fırlat
            if request_count >= max_requests:
                retry_after = per_seconds - time_diff if time_diff < per_seconds else 1
                # Kullanıcı bilgilerinden PII koruma için sadece ID'nin bir kısmını logla
                masked_user_id = user_id[:5] + '***' if user_id and len(user_id) > 5 else 'anonymous'
                logger.warning(
                    f"Rate limit exceeded - IP: {client_ip}, User: {masked_user_id}, Endpoint: {endpoint}"
                )
                
                raise HTTPException(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Çok fazla istek. Lütfen {int(retry_after)} saniye sonra tekrar deneyin.",
                    headers={"Retry-After": str(int(retry_after))}
                )

            # Sayacı güncelle
            self.rate_limit_storage[identifier] = (request_count + 1, last_request)

            # Debug seviyesinde loglama
            if settings.DEBUG:
                # Kullanıcı bilgilerinden PII koruma için sadece ID'nin bir kısmını logla
                masked_user_id = user_id[:5] + '***' if user_id and len(user_id) > 5 else 'anonymous'
                logger.debug(
                    f"Rate limit check - IP: {client_ip}, User: {masked_user_id}, Endpoint: {endpoint}, Count: {request_count + 1}/{max_requests}"
                )

    # FastAPI dependency olarak kullanılabilecek method
    async def __call__(self, request: Request):
        """
        FastAPI dependency olarak kullanım için.
        
        Args:
            request: FastAPI istek nesnesi
            
        Returns:
            Request: Aynı istek nesnesi (rate limit kontrolü başarılı ise)
        """
        await self.check_rate_limit(request)
        return request
        
    # Decorator factory methodu
    def limit(self, rate_limit_string: str = None):
        """
        Endpoint'lere rate limit uygulamak için decorator.
        
        Args:
            rate_limit_string: İsteğe bağlı oran limiti (örn: "100/minute", "5/second")
            
        Returns:
            Callable: Dekoratör fonksiyon
        """
        # Rate limit string'i parse et veya varsayılanları kullan
        requests = settings.DEFAULT_RATE_LIMIT_REQUESTS
        per_seconds = settings.DEFAULT_RATE_LIMIT_SECONDS
        
        if rate_limit_string:
            try:
                requests_str, time_unit = rate_limit_string.split("/")
                requests = int(requests_str)
                
                if time_unit in ["second", "seconds"]:
                    per_seconds = 1
                elif time_unit in ["minute", "minutes"]:
                    per_seconds = 60
                elif time_unit in ["hour", "hours"]:
                    per_seconds = 3600
                elif time_unit in ["day", "days"]:
                    per_seconds = 86400
            except (ValueError, IndexError):
                logger.warning(f"Geçersiz rate limit formatı: {rate_limit_string}, varsayılanlar kullanılıyor")
        
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
                await self.check_rate_limit(request, requests=requests, per_seconds=per_seconds)
                return await func(request, *args, **kwargs)
            return wrapper
        return decorator


class RateLimitBearer(HTTPBearer):
    """
    Bearer token içeren istekler için rate limit uygulayan HTTP Bearer sınıfı.
    Token'dan kullanıcı kimliğini çıkararak kişiye özel rate limiting uygular.
    """
    def __init__(self, auto_error: bool = True, rate_limit_string: Optional[str] = None):
        """
        Args:
            auto_error: Token eksikliğinde otomatik hata fırlatma
            rate_limit_string: Özel rate limit tanımı (örn: "100/minute")
        """
        super().__init__(auto_error=auto_error)
        self.rate_limiter = RateLimiter()
        
        # Özel rate limit varsa parse et
        self.requests = None
        self.per_seconds = None
        
        if rate_limit_string:
            try:
                requests_str, time_unit = rate_limit_string.split("/")
                self.requests = int(requests_str)
                
                if time_unit in ["second", "seconds"]:
                    self.per_seconds = 1
                elif time_unit in ["minute", "minutes"]:
                    self.per_seconds = 60
                elif time_unit in ["hour", "hours"]:
                    self.per_seconds = 3600
                elif time_unit in ["day", "days"]:
                    self.per_seconds = 86400
            except (ValueError, IndexError):
                logger.warning(f"Geçersiz rate limit formatı: {rate_limit_string}")

    async def __call__(self, request: Request):
        """
        HTTP Bearer token içeren istekleri intercept eder ve rate limit uygular.
        
        Args:
            request: FastAPI istek nesnesi
            
        Returns:
            HTTPAuthorizationCredentials: Bearer token bilgileri
        """
        # Token bilgilerini al
        credentials = await super().__call__(request)
        
        # Token'dan kullanıcı ID'sini çıkar
        user_id = await self._get_user_id_from_token(credentials.credentials)
        
        # Rate limit kontrolü
        await self.rate_limiter.check_rate_limit(
            request, 
            user_id=user_id,
            requests=self.requests,
            per_seconds=self.per_seconds
        )
        
        return credentials

    async def _get_user_id_from_token(self, token: str) -> Optional[str]:
        """
        JWT token'dan kullanıcı ID'sini çıkarır.
        
        Args:
            token: JWT token string
            
        Returns:
            Optional[str]: Kullanıcı ID'si veya None
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload.get("sub")  # JWT standardına göre sub claim'i kullanıcı ID'sidir
        except JWTError:
            return None


# Global rate limiter instance
limiter = RateLimiter()

# Geriye dönük uyumluluk için eski tarz decorator fonksiyonu
def rate_limit(rate_limit_string: str = None):
    """
    Endpoint için rate limit decorator'ı (eski stil).
    Yeni projelerde doğrudan limiter.limit() kullanılması önerilir.
    
    Args:
        rate_limit_string: Rate limit tanımı (örn: "100/minute")
        
    Returns:
        Decorator fonksiyon
    """
    return limiter.limit(rate_limit_string)