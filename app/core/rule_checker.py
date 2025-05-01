"""
RuleChecker – Firma Bazlı Kural Denetleyicisi
---------------------------------------------
Bu sınıf, sistemde tenant'a (firmaya) özel tanımlanmış kuralları kontrol eder.
Her tenant, kendi `settings` alanı üzerinden proje yönetim tarzına uygun kurallar tanımlar.
Kullanım:
    await RuleChecker.ensure_document_uploaded(tenant_settings, proje_id)
Geliştirici Notu:
- Her kural, sistemin farklı yerlerinde tetiklenebilir.
- Kural yoksa varsayılan değeri kullanılır.
- Kural ihlali durumunda otomatik HTTPException fırlatılır.
"""
from fastapi import HTTPException, status, Request, Depends
from typing import Dict, Any, Optional, Type, TypeVar, cast, List
from app.utils.database import db_manager, COLLECTIONS
from app.core.tenant_db import get_tenant_settings
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')

class RuleChecker:
    @staticmethod
    def get_setting(settings: Dict[str, Any], key: str, default_value: Any = None, 
                    required: bool = False, value_type: Optional[Type[T]] = None) -> T:
        """
        Ayarlardan güvenli bir şekilde değer alır
        
        Args:
            settings: Firma ayarları sözlüğü
            key: Alınacak ayar anahtarı
            default_value: Ayar bulunamazsa kullanılacak varsayılan değer
            required: True ise ve ayar bulunamazsa hata fırlatır
            value_type: Belirtilirse, değerin bu tipte olmasını sağlar
            
        Returns:
            Ayarın değeri veya varsayılan değer
            
        Raises:
            HTTPException: Gerekli ayar bulunamadığında veya tip dönüşümü başarısız olduğunda
        """
        if not settings:
            if required:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Firma ayarları bulunamadı."
                )
            return cast(T, default_value)
            
        value = settings.get(key, default_value)
        
        if value is None and required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Gerekli ayar '{key}' bulunamadı."
            )
        
        if value_type and value is not None:
            try:
                value = value_type(value)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ayar '{key}' beklenen tipte değil. Beklenen: {value_type.__name__}"
                )
                
        return cast(T, value)

    @staticmethod
    async def ensure_customer_approval(settings: Dict[str, Any], tenant_db: Optional[AsyncIOMotorDatabase] = None):
        """
        Müşteri onayı zorunluysa kontrol eder
        
        Args:
            settings: Tenant ayarları
            tenant_db: Tenant veritabanı bağlantısı (opsiyonel)
            
        Raises:
            HTTPException: Onay zorunlu ve alınmamışsa
        """
        if RuleChecker.get_setting(settings, "require_customer_approval", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için müşteri onayı gereklidir. Lütfen önce müşteriden onay alınız."
            )
    
    @staticmethod
    async def ensure_document_uploaded(
        settings: Dict[str, Any], 
        proje_id: str, 
        tenant_db: Optional[AsyncIOMotorDatabase] = None
    ):
        """
        Belge yüklenmeden proje başlatılamaz mı?
        
        Args:
            settings: Tenant ayarları
            proje_id: Proje ID
            tenant_db: Tenant veritabanı bağlantısı (opsiyonel)
            
        Raises:
            HTTPException: Belge yüklenmeden işlem yapılamıyorsa
        """
        if not proje_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Proje ID belirtilmedi."
            )
            
        if not RuleChecker.get_setting(settings, "document_upload_required", False):
            return  # kural pasif, devam edilebilir
            
        required_doc_types = RuleChecker.get_setting(
            settings, 
            "document_types_required", 
            ["sozlesme"]
        )
        
        if tenant_db is None:
            logger.warning("ensure_document_uploaded: tenant_db parametresi belirtilmemiş, veritabanı erişimi yapılamıyor.")
            # Burada tenant_db olmadığında ne yapacağını belirlemeliyiz
            # Bu durumda kuralı atlayabilir veya hata fırlatabilirsiniz
            return
        
        belge_var = await tenant_db[COLLECTIONS.DOCUMENTS].find_one({
            "proje_id": proje_id,
            "tur": {"$in": required_doc_types}
        })
        
        if not belge_var:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zorunlu belgeler ({', '.join(required_doc_types)}) yüklenmeden bu işlem yapılamaz."
            )
    
    @staticmethod
    async def ensure_nfc_required(settings: Dict[str, Any], manuel_giris: bool = False):
        """
        NFC zorunluysa, manuel giriş yapılamaz
        
        Args:
            settings: Tenant ayarları
            manuel_giris: Manuel giriş yapılmak isteniyorsa True
            
        Raises:
            HTTPException: NFC zorunlu ve manuel giriş yapılmaya çalışılıyorsa
        """
        # Eğer NFC takibi etkinse VE manuel giriş yapılmaya çalışılıyorsa hata fırlat
        if RuleChecker.get_setting(settings, "nfc_tracking_enabled", False) and manuel_giris:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu firma için NFC ile giriş zorunludur. Manuel giriş yapılamaz."
            )
    
    @staticmethod
    async def ensure_material_ready(settings: Dict[str, Any], material_delivered: bool):
        """
        Malzeme gelmeden iş başlatılamaz mı?
        
        Args:
            settings: Tenant ayarları
            material_delivered: Malzeme teslim alındı mı?
            
        Raises:
            HTTPException: Malzeme zorunlu ve teslim alınmadıysa
        """
        if RuleChecker.get_setting(settings, "require_material_before_start", True) and not material_delivered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malzeme sahaya gelmeden iş başlatılamaz. Önce malzeme teslimatını onaylayınız."
            )
    
    @staticmethod
    async def ensure_user_has_role(user_role: str, settings: Dict[str, Any], action: str):
        """
        Bu işlemi sadece belirli roller yapabilir mi?
        
        Args:
            user_role: Kullanıcı rolü
            settings: Tenant ayarları
            action: İşlem türü (create, update, delete gibi)
            
        Raises:
            HTTPException: Kullanıcının bu işlem için yetkisi yoksa
        """
        if not user_role or not action:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rol ve yetki kontrolü için gerekli bilgiler eksik."
            )
            
        allowed_roles = RuleChecker.get_setting(
            settings, 
            f"allowed_roles_for_{action}", 
            ["admin"]
        )
        
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu işlem için yetkiniz bulunmuyor. Gereken rol(ler): {', '.join(allowed_roles)}"
            )
    
    @staticmethod
    async def validate_permissions_for_action(
        settings: Dict[str, Any], 
        user_permissions: List[str], 
        required_permission: str
    ):
        """
        Kullanıcının belirli bir işlem için gereken izinleri var mı?
        
        Args:
            settings: Tenant ayarları
            user_permissions: Kullanıcının sahip olduğu izinler
            required_permission: Gereken izin
            
        Raises:
            HTTPException: Kullanıcının gereken izni yoksa
        """
        # Admin her zaman tüm izinlere sahiptir
        if "admin" in user_permissions:
            return
            
        is_strict_mode = RuleChecker.get_setting(settings, "strict_permission_mode", False)
        
        if is_strict_mode and required_permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu işlem için '{required_permission}' iznine sahip olmanız gerekiyor."
            )

# Dependency olarak kullanılabilecek fonksiyonlar
async def get_rule_checker(request: Request) -> RuleChecker:
    """
    RuleChecker sınıfını dependency olarak kullanılabilir hale getirir
    
    Args:
        request: FastAPI request nesnesi
        
    Returns:
        RuleChecker: Kural denetleyici sınıfı
    """
    return RuleChecker()

async def validate_rule(
    request: Request,
    rule_name: str,
    tenant_settings: Dict[str, Any] = Depends(get_tenant_settings)
):
    """
    İsim verilen kuralı validate eden dependency fonksiyonu
    
    Args:
        request: FastAPI request nesnesi
        rule_name: Kontrol edilecek kural adı
        tenant_settings: Tenant ayarları (dependency olarak alınır)
        
    Raises:
        HTTPException: Kural ihlal edilirse veya kural bulunamazsa
    """
    if rule_name == "customer_approval":
        await RuleChecker.ensure_customer_approval(tenant_settings)
    elif rule_name == "nfc_required":
        await RuleChecker.ensure_nfc_required(tenant_settings, manuel_giris=True)
    elif rule_name == "material_ready":
        # Burada material_delivered değerini request body'den alabiliriz
        body = await request.json()
        material_delivered = body.get("material_delivered", False)
        await RuleChecker.ensure_material_ready(tenant_settings, material_delivered)
    else:
        logger.warning(f"Bilinmeyen kural adı: {rule_name}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bilinmeyen kural: {rule_name}"
        )