"""
tenant_db.py – Dinamik Tenant Veritabanı Seçimi
-----------------------------------------------
Bu modül, her istek sırasında token içinden tenant_id alınarak
ilgili firmanın veritabanı bağlantısını döndürür.
Her firma kendi izole MongoDB veritabanında çalışır.
"""
from fastapi import Request, HTTPException, status, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.config import settings
from app.utils.database import db_manager, COLLECTIONS
from jose import JWTError, jwt
from typing import Optional, Dict, Any, Tuple
from cachetools import TTLCache, cached
import logging

logger = logging.getLogger(__name__)

# Performans için tenant bilgilerini önbelleğe alma (10 dakika TTL)
tenant_cache = TTLCache(maxsize=100, ttl=600)

@cached(cache=tenant_cache)
async def get_tenant_info(tenant_id: str) -> dict:
    """
    Tenant bilgilerini veritabanından alır, önbellek kullanır.
    
    Args:
        tenant_id: Tenant ID
        
    Returns:
        dict: Tenant bilgileri
        
    Raises:
        HTTPException: Tenant bulunamazsa
    """
    # Bağlantı kontrolü
    await db_manager.validate_connection()
    
    tenant = await db_manager.main_db[COLLECTIONS.TENANTS].find_one({"_id": tenant_id})
    if not tenant:
        logger.warning(f"Tenant bulunamadı: {tenant_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firma bulunamadı")
        
    return tenant

async def get_tenant_db(request: Request = None, tenant_id: str = None) -> AsyncIOMotorDatabase:
    """
    Her istek için tenant'a özel veritabanı döndürür.
    Token içindeki tenant_id'den ilgili veritabanı adı alınır.
    
    Args:
        request: FastAPI request nesnesi
        tenant_id: Doğrudan tenant_id belirtilirse, token kontrolü yapılmaz
        
    Returns:
        AsyncIOMotorDatabase: Tenant'a ait veritabanı nesnesi
        
    Raises:
        HTTPException: Token veya tenant ile ilgili hata durumunda
    """
    # tenant_id doğrudan verilmişse token kontrolü atlanır
    if tenant_id is None and request is not None:
        tenant_id = await _extract_tenant_id_from_request(request)
    elif tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID veya Request belirtilmelidir"
        )
    
    # tenant_id'ye göre database_name bulunur (önbellekten)
    try:
        tenant = await get_tenant_info(tenant_id)
    except HTTPException:
        raise  # Önceki hatayı tekrar fırlat
    
    database_name = tenant.get("database_name")
    if not database_name:
        logger.error(f"Tenant için veritabanı adı tanımlanmamış: {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Firma için veritabanı adı tanımlanmamış"
        )
    
    # Veritabanı bağlantısını kontrol et
    await db_manager.validate_connection()
    
    # Veritabanı nesnesi döndürülür
    return db_manager.get_db(database_name)

async def get_tenant_settings(request: Request = None, tenant_id: str = None) -> Tuple[Dict[str, Any], AsyncIOMotorDatabase]:
    """
    Tenant'ın ayarlarını ve veritabanı nesnesini döndürür
    
    Args:
        request: FastAPI request nesnesi
        tenant_id: Doğrudan tenant_id belirtilirse, token kontrolü yapılmaz
        
    Returns:
        Tuple[Dict, AsyncIOMotorDatabase]: Tenant ayarları ve veritabanı nesnesi
        
    Raises:
        HTTPException: Hata durumunda
    """
    if tenant_id is None and request is not None:
        tenant_id = await _extract_tenant_id_from_request(request)
    elif tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID veya Request belirtilmelidir"
        )
    
    tenant_db = await get_tenant_db(tenant_id=tenant_id)
    
    # Önce ana tenant bilgilerini al
    tenant = await get_tenant_info(tenant_id)
    
    # Sonra tenant-spesifik ayarları al
    tenant_settings = await tenant_db[COLLECTIONS.SETTINGS].find_one({"tenant_id": tenant_id})
    if not tenant_settings:
        # Tenant-spesifik ayarlar bulunamazsa varsayılan ayarları oluştur
        tenant_settings = {
            "tenant_id": tenant_id,
            "default_settings": True,
            # Burada varsayılan ayarları belirleyebilirsiniz
            "require_customer_approval": False,
            "document_upload_required": False,
            "document_types_required": ["sozlesme"],
            "nfc_tracking_enabled": False,
            "require_material_before_start": True,
            # Role-based permissions default
            "allowed_roles_for_project_create": ["admin", "manager"],
            "allowed_roles_for_expense_create": ["admin", "manager", "user"],
            "allowed_roles_for_material_create": ["admin", "manager", "user"],
        }
        
        # Varsayılan ayarları kaydet
        await tenant_db[COLLECTIONS.SETTINGS].insert_one(tenant_settings)
        logger.info(f"Tenant için varsayılan ayarlar oluşturuldu: {tenant_id}")
    
    # Ana tenant bilgilerinden bazı ayarları ekle
    merged_settings = {**tenant_settings}
    
    # Önemli tenant bilgilerini ekle
    for key in ["license_type", "max_users", "is_active"]:
        if key in tenant:
            merged_settings[key] = tenant[key]
    
    return merged_settings, tenant_db

async def _extract_tenant_id_from_request(request: Request) -> str:
    """
    İstek içindeki token'dan tenant_id çıkarır. 
    get_tenant_db ile kod tekrarını önlemek için yardımcı fonksiyon.
    
    Args:
        request: FastAPI request nesnesi
        
    Returns:
        str: Tenant ID
        
    Raises:
        HTTPException: Token hatası durumunda
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token eksik veya geçersiz format"
        )
    
    token = auth_header.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER
        )
    except JWTError as e:
        logger.warning(f"Token doğrulama hatası: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=f"Token doğrulama başarısız: {str(e)}"
        )
    
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        logger.warning("Token içinde tenant_id bilgisi bulunamadı")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token içinde tenant_id bilgisi bulunamadı"
        )
    
    return tenant_id

# Dependency olarak kullanılabilecek yardımcı fonksiyonlar
async def get_tenant_id_from_token(request: Request) -> str:
    """
    Token'dan tenant_id çeken ve dependency olarak kullanılabilecek fonksiyon
    
    Args:
        request: FastAPI request nesnesi
        
    Returns:
        str: Tenant ID
    """
    return await _extract_tenant_id_from_request(request)