"""
Proje servis modülü, proje varlıklarının oluşturulması, düzenlenmesi, silinmesi ve sorgulanmasından sorumludur.
Bu modül aşağıdaki işlemleri gerçekleştirir:

- Proje Yönetimi: Projelerin oluşturulması, güncellenmesi ve silinmesi
- İzin Kontrolü: Proje işlemleri için kullanıcı izinlerinin doğrulanması
- Veri Doğrulama: Giriş verilerinin doğrulanması ve temizlenmesi
- İş Kuralları: Proje işlemlerinde iş kurallarının uygulanması
- İstatistik ve Raporlama: Proje istatistiklerinin hesaplanması

Bu modül, proje ile ilgili tüm business logic'i encapsule eder ve veri erişimi 
ile sunum katmanları arasında bir abstraction layer sağlar.
"""

from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any, Union
from bson import ObjectId
from fastapi import HTTPException, status

from app.utils.database import db_manager, COLLECTIONS
from app.schemas.project import (
    ProjectCreate, 
    ProjectUpdate, 
    ProjectOut, 
    ProjectList,
    ProjectStatsResponse
)
from app.utils.logger import logger
from app.utils.pagination import PaginationParams

UTC_TZ = timezone.utc

class ProjectService:
    """
    Proje işlemlerini yöneten servis sınıfı.
    Projelerle ilgili tüm veritabanı işlemleri ve iş mantığı bu sınıfta yönetilir.
    """
    
    def __init__(self):
        """Servis sınıfı başlatıcısı."""
        # Her kiracı için ayrı veritabanı olduğundan, 
        # Tenant ID alındıktan sonra ilgili veritabanına bağlanılır
        pass
        
    async def create_project(
        self, 
        tenant_id: str, 
        user_id: str, 
        data: ProjectCreate
    ) -> ProjectOut:
        """
        Yeni bir proje oluşturur.
        
        Args:
            tenant_id: Projenin ait olduğu kiracı ID'si
            user_id: Projeyi oluşturan kullanıcı ID'si
            data: Proje oluşturma verileri
            
        Returns:
            ProjectOut: Oluşturulan proje detayları
            
        Raises:
            HTTPException: Proje oluşturma sırasında hata oluşursa
        """
        try:
            # Veri doğrulama işlemleri
            if not tenant_id or not ObjectId.is_valid(tenant_id):
                raise ValueError("Geçersiz tenant ID")
                
            # İzin kontrolü (burada güvenlik katmanı tarafından yapıldığı varsayılmıştır)
            
            # Kiracıya özel DB'ye bağlan
            tenant_db = db_manager.get_tenant_db(tenant_id)
            
            # Proje verisini hazırla
            current_time = datetime.now(UTC_TZ)
            project_data = data.model_dump()
            
            # Ek veri alanlarını ekle
            project_data.update({
                "tenant_id": tenant_id,
                "created_by": user_id,
                "created_at": current_time,
                "updated_at": current_time,
                "updated_by": user_id
            })
            
            # Proje adının benzersiz olduğunu kontrol et
            existing_project = await tenant_db[COLLECTIONS.PROJECTS].find_one({
                "name": project_data["name"],
                "tenant_id": tenant_id
            })
            
            if existing_project:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Bu isimde bir proje zaten mevcut"
                )
                
            # Projeyi veritabanına ekle
            result = await tenant_db[COLLECTIONS.PROJECTS].insert_one(project_data)
            
            if not result.inserted_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Proje oluşturulamadı"
                )
                
            # Oluşturulan projeyi getir
            created_project = await tenant_db[COLLECTIONS.PROJECTS].find_one(
                {"_id": result.inserted_id}
            )
            
            if not created_project:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Proje oluşturuldu ancak getirilemedi"
                )
                
            # Audit log
            await self._add_project_audit_log(
                tenant_id=tenant_id,
                project_id=str(result.inserted_id),
                user_id=user_id,
                action="create",
                details="Proje oluşturuldu"
            )
            
            return ProjectOut(**created_project)
            
        except HTTPException as http_ex:
            # HTTP exception'ları doğrudan ilet
            raise http_ex
        except ValueError as val_err:
            # Doğrulama hatalarını HTTP 400 olarak ilet
            logger.warning(f"Proje oluşturma doğrulama hatası: {str(val_err)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err)
            )
        except Exception as e:
            # Beklenmeyen hataları logla ve genel bir hata döndür
            logger.error(f"Proje oluşturma hatası: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Proje oluşturma işlemi sırasında beklenmeyen bir hata oluştu"
            )
            
    async def list_projects(
        self, 
        filters: Dict[str, Any], 
        skip: int = 0, 
        limit: int = 10,
        sort: List[Tuple[str, int]] = None
    ) -> Tuple[List[ProjectOut], int]:
        """
        Filtrelere göre projeleri listeler.
        
        Args:
            filters: Filtreleme kriterleri
            skip: Atlanacak kayıt sayısı
            limit: Alınacak maksimum kayıt sayısı
            sort: Sıralama kriterleri [(alan_adı, yön)]
            
        Returns:
            Tuple[List[ProjectOut], int]: Proje listesi ve toplam kayıt sayısı
        """
        try:
            if not filters or "tenant_id" not in filters:
                raise ValueError("Tenant ID gereklidir")
                
            tenant_id = filters["tenant_id"]
            tenant_db = db_manager.get_tenant_db(tenant_id)
            
            # Sıralama belirtilmemişse son oluşturulana göre sırala
            if not sort:
                sort = [("created_at", -1)]
                
            # Projeleri getir
            cursor = tenant_db[COLLECTIONS.PROJECTS].find(filters)
            
            # Sıralama uygula
            for field, direction in sort:
                cursor = cursor.sort(field, direction)
                
            # Sayfalama uygula
            cursor = cursor.skip(skip).limit(limit)
            
            # Sonuçları al
            projects = await cursor.to_list(length=limit)
            
            # Toplam kayıt sayısını al
            total = await tenant_db[COLLECTIONS.PROJECTS].count_documents(filters)
            
            # Proje listesini doğrula ve dönüştür
            project_list = [ProjectOut(**project) for project in projects]
            
            return project_list, total
            
        except Exception as e:
            logger.error(f"Proje listeleme hatası: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Projeler listelenirken bir hata oluştu"
            )
            
    async def get_project_by_id(
        self, 
        tenant_id: str, 
        project_id: str
    ) -> Optional[ProjectOut]:
        """
        ID'ye göre proje detaylarını getirir.
        
        Args:
            tenant_id: Kiracı ID'si
            project_id: Proje ID'si
            
        Returns:
            Optional[ProjectOut]: Proje detayları veya None
        """
        try:
            if not ObjectId.is_valid(project_id):
                raise ValueError("Geçersiz proje ID formatı")
                
            tenant_db = db_manager.get_tenant_db(tenant_id)
            
            project = await tenant_db[COLLECTIONS.PROJECTS].find_one({
                "_id": ObjectId(project_id),
                "tenant_id": tenant_id
            })
            
            if not project:
                return None
                
            return ProjectOut(**project)
            
        except ValueError as val_err:
            logger.warning(f"Proje getirme doğrulama hatası: {str(val_err)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err)
            )
        except Exception as e:
            logger.error(f"Proje getirme hatası: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Proje bilgileri alınırken bir hata oluştu"
            )
            
    async def update_project(
        self, 
        tenant_id: str, 
        project_id: str, 
        user_id: str, 
        data: ProjectUpdate
    ) -> ProjectOut:
        """
        Proje bilgilerini günceller.
        
        Args:
            tenant_id: Kiracı ID'si
            project_id: Proje ID'si
            user_id: Güncellemeyi yapan kullanıcı ID'si
            data: Güncellenecek proje verileri
            
        Returns:
            ProjectOut: Güncellenmiş proje detayları
            
        Raises:
            HTTPException: Güncelleme sırasında hata oluşursa
        """
        try:
            if not ObjectId.is_valid(project_id):
                raise ValueError("Geçersiz proje ID formatı")
                
            tenant_db = db_manager.get_tenant_db(tenant_id)
            
            # Projenin var olduğunu kontrol et
            existing_project = await tenant_db[COLLECTIONS.PROJECTS].find_one({
                "_id": ObjectId(project_id),
                "tenant_id": tenant_id
            })
            
            if not existing_project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Proje bulunamadı"
                )
                
            # Proje adı değişiyorsa benzersizlik kontrolü yap
            update_data = data.model_dump(exclude_unset=True)
            
            if "name" in update_data and update_data["name"] != existing_project.get("name"):
                name_exists = await tenant_db[COLLECTIONS.PROJECTS].find_one({
                    "name": update_data["name"],
                    "tenant_id": tenant_id,
                    "_id": {"$ne": ObjectId(project_id)}
                })
                
                if name_exists:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Bu isimde başka bir proje zaten mevcut"
                    )
            
            # Güncelleme verilerini hazırla
            update_data["updated_at"] = datetime.now(UTC_TZ)
            update_data["updated_by"] = user_id
            
            # Projeyi güncelle
            result = await tenant_db[COLLECTIONS.PROJECTS].update_one(
                {"_id": ObjectId(project_id)},
                {"$set": update_data}
            )
            
            if result.modified_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    detail="Proje güncellenmedi"
                )
                
            # Güncellenmiş projeyi getir
            updated_project = await tenant_db[COLLECTIONS.PROJECTS].find_one(
                {"_id": ObjectId(project_id)}
            )
            
            # Audit log
            await self._add_project_audit_log(
                tenant_id=tenant_id,
                project_id=project_id,
                user_id=user_id,
                action="update",
                details=f"Proje güncellendi: {', '.join(update_data.keys())}"
            )
            
            return ProjectOut(**updated_project)
            
        except HTTPException as http_ex:
            raise http_ex
        except ValueError as val_err:
            logger.warning(f"Proje güncelleme doğrulama hatası: {str(val_err)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err)
            )
        except Exception as e:
            logger.error(f"Proje güncelleme hatası: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Proje güncellenirken bir hata oluştu"
            )
            
    async def delete_project(
        self, 
        tenant_id: str, 
        project_id: str, 
        user_id: str
    ) -> bool:
        """
        Projeyi siler.
        
        Args:
            tenant_id: Kiracı ID'si
            project_id: Silinecek proje ID'si
            user_id: İşlemi yapan kullanıcı ID'si
            
        Returns:
            bool: Silme işlemi başarılı ise True
            
        Raises:
            HTTPException: Silme sırasında hata oluşursa
        """
        try:
            if not ObjectId.is_valid(project_id):
                raise ValueError("Geçersiz proje ID formatı")
                
            tenant_db = db_manager.get_tenant_db(tenant_id)
            
            # Projenin var olduğunu kontrol et
            existing_project = await tenant_db[COLLECTIONS.PROJECTS].find_one({
                "_id": ObjectId(project_id),
                "tenant_id": tenant_id
            })
            
            if not existing_project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Proje bulunamadı"
                )
                
            # İlişkili kaynakları kontrol et (malzemeler, personel, vb.)
            # Burada ilişkili kaynakların kontrolü ve/veya silinmesi eklenebilir
            
            # Projeyi sil
            result = await tenant_db[COLLECTIONS.PROJECTS].delete_one({
                "_id": ObjectId(project_id)
            })
            
            if result.deleted_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Proje silinemedi"
                )
                
            # Audit log
            await self._add_project_audit_log(
                tenant_id=tenant_id,
                project_id=project_id,
                user_id=user_id,
                action="delete",
                details="Proje silindi"
            )
            
            return True
            
        except HTTPException as http_ex:
            raise http_ex
        except ValueError as val_err:
            logger.warning(f"Proje silme doğrulama hatası: {str(val_err)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err)
            )
        except Exception as e:
            logger.error(f"Proje silme hatası: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Proje silinirken bir hata oluştu"
            )
            
    async def get_project_stats(
        self, 
        tenant_id: str, 
        project_id: str
    ) -> ProjectStatsResponse:
        """
        Proje istatistiklerini hesaplar ve getirir.
        
        Args:
            tenant_id: Kiracı ID'si
            project_id: Proje ID'si
            
        Returns:
            ProjectStatsResponse: Proje istatistikleri
        """
        try:
            if not ObjectId.is_valid(project_id):
                raise ValueError("Geçersiz proje ID formatı")
                
            tenant_db = db_manager.get_tenant_db(tenant_id)
            
            # Projenin var olduğunu kontrol et
            project = await tenant_db[COLLECTIONS.PROJECTS].find_one({
                "_id": ObjectId(project_id),
                "tenant_id": tenant_id
            })
            
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Proje bulunamadı"
                )
                
            # İstatistik ve analiz bilgilerini hesapla
            # Örnek: Görev durumları, bütçe kullanımı, tamamlanma yüzdesi vb.
            
            # Proje görevlerini getir
            tasks = await tenant_db[COLLECTIONS.TASKS].find({
                "project_id": project_id
            }).to_list(length=1000)
            
            # Proje malzemelerini getir
            materials = await tenant_db[COLLECTIONS.PROJECT_MATERIALS].find({
                "project_id": project_id
            }).to_list(length=1000)
            
            # Proje personelini getir
            personnel = await tenant_db[COLLECTIONS.PROJECT_PERSONNEL].find({
                "project_id": project_id
            }).to_list(length=1000)
            
            # İstatistikleri hesapla
            total_tasks = len(tasks)
            completed_tasks = sum(1 for task in tasks if task.get("status") == "completed")
            
            task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            
            # Bütçe kullanımı
            planned_budget = project.get("budget", 0)
            used_budget = sum(material.get("cost", 0) * material.get("quantity", 0) for material in materials)
            
            # Zaman kullanımı
            start_date = project.get("start_date")
            end_date = project.get("end_date")
            current_time = datetime.now(UTC_TZ)
            
            total_days = (end_date - start_date).days if start_date and end_date else 0
            elapsed_days = (current_time - start_date).days if start_date else 0
            
            time_progress = (elapsed_days / total_days * 100) if total_days > 0 else 0
            
            # İstatistik sonuçlarını oluştur
            stats = {
                "project_id": project_id,
                "name": project.get("name"),
                "task_stats": {
                    "total": total_tasks,
                    "completed": completed_tasks,
                    "completion_rate": task_completion_rate
                },
                "budget_stats": {
                    "planned": planned_budget,
                    "used": used_budget,
                    "remaining": planned_budget - used_budget,
                    "usage_rate": (used_budget / planned_budget * 100) if planned_budget > 0 else 0
                },
                "resource_stats": {
                    "total_materials": len(materials),
                    "total_personnel": len(personnel)
                },
                "time_stats": {
                    "total_days": total_days,
                    "elapsed_days": elapsed_days,
                    "time_progress": time_progress
                }
            }
            
            return ProjectStatsResponse(**stats)
            
        except HTTPException as http_ex:
            raise http_ex
        except ValueError as val_err:
            logger.warning(f"Proje istatistikleri doğrulama hatası: {str(val_err)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err)
            )
        except Exception as e:
            logger.error(f"Proje istatistikleri hatası: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Proje istatistikleri hesaplanırken bir hata oluştu"
            )
            
    async def _add_project_audit_log(
        self, 
        tenant_id: str, 
        project_id: str, 
        user_id: str, 
        action: str, 
        details: str
    ) -> bool:
        """
        Proje işlemleri için denetim logu ekler.
        
        Args:
            tenant_id: Kiracı ID'si
            project_id: Proje ID'si
            user_id: İşlemi yapan kullanıcı ID'si
            action: Gerçekleştirilen eylem (create, update, delete, vb.)
            details: İşlem detayları
            
        Returns:
            bool: Log ekleme başarılı ise True
        """
        try:
            tenant_db = db_manager.get_tenant_db(tenant_id)
            
            # Denetim logu oluştur
            log_entry = {
                "tenant_id": tenant_id,
                "entity_type": "project",
                "entity_id": project_id,
                "user_id": user_id,
                "action": action,
                "details": details,
                "timestamp": datetime.now(UTC_TZ),
                "ip_address": "",  # İstemci IP'si burada eklenebilir
                "user_agent": ""   # Kullanıcı ajanı bilgisi burada eklenebilir
            }
            
            # Denetim logunu veritabanına ekle
            await tenant_db[COLLECTIONS.AUDIT_LOGS].insert_one(log_entry)
            
            return True
            
        except Exception as e:
            logger.error(f"Denetim logu ekleme hatası: {str(e)}", exc_info=True)
            # Audit log ekleme hataları ana işlemi etkilememeli
            return False