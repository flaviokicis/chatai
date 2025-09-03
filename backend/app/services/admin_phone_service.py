"""Service for managing and checking admin phone numbers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AdminPhoneService:
    """Service for checking admin phone numbers and managing admin privileges."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def is_admin_phone(self, phone_number: str, tenant_id: UUID) -> bool:
        """
        Check if a phone number is in the admin list for a tenant.
        
        Args:
            phone_number: Phone number to check (e.g., "+5511999999999" or "whatsapp:+5511999999999")
            tenant_id: Tenant ID to check against
            
        Returns:
            True if the phone number is an admin, False otherwise
        """
        try:
            from app.db.models import Tenant

            # Normalize phone number - remove whatsapp: prefix and non-digit characters, ensure + prefix
            def normalize(p: str) -> str:
                p2 = p.replace("whatsapp:", "").replace(" ", "").strip()
                # Keep leading + and digits only
                if p2.startswith("+"):
                    sign = "+"
                    digits = "".join(ch for ch in p2 if ch.isdigit())
                    return sign + digits
                digits = "".join(ch for ch in p2 if ch.isdigit())
                return "+" + digits if digits else p2

            normalized_phone = normalize(phone_number)

            # Get tenant with admin phone numbers
            tenant = self.session.get(Tenant, tenant_id)
            if not tenant or not tenant.admin_phone_numbers:
                return False

            # Check if normalized phone is in the admin list
            admin_phones = tenant.admin_phone_numbers or []
            normalized_admins = {normalize(p) for p in admin_phones}
            return normalized_phone in normalized_admins

        except Exception as e:
            logger.error(f"Error checking admin phone {phone_number} for tenant {tenant_id}: {e}")
            return False

    def add_admin_phone(self, phone_number: str, tenant_id: UUID) -> bool:
        """
        Add a phone number to the admin list for a tenant.
        
        Args:
            phone_number: Phone number to add (will be normalized)
            tenant_id: Tenant ID to add to
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            from app.db.models import Tenant

            # Normalize phone number
            normalized_phone = phone_number.replace("whatsapp:", "").strip()

            # Get tenant
            tenant = self.session.get(Tenant, tenant_id)
            if not tenant:
                return False

            # Initialize admin_phone_numbers if None
            if tenant.admin_phone_numbers is None:
                tenant.admin_phone_numbers = []

            # Add phone if not already present
            if normalized_phone not in tenant.admin_phone_numbers:
                tenant.admin_phone_numbers.append(normalized_phone)
                # Mark the field as modified for SQLAlchemy to detect the change
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(tenant, "admin_phone_numbers")
                self.session.commit()
                logger.info(f"Added admin phone {normalized_phone} to tenant {tenant_id}")

            return True

        except Exception as e:
            logger.error(f"Error adding admin phone {phone_number} to tenant {tenant_id}: {e}")
            self.session.rollback()
            return False

    def remove_admin_phone(self, phone_number: str, tenant_id: UUID) -> bool:
        """
        Remove a phone number from the admin list for a tenant.
        
        Args:
            phone_number: Phone number to remove (will be normalized)
            tenant_id: Tenant ID to remove from
            
        Returns:
            True if removed successfully, False otherwise
        """
        try:
            from app.db.models import Tenant

            # Normalize phone number
            normalized_phone = phone_number.replace("whatsapp:", "").strip()

            # Get tenant
            tenant = self.session.get(Tenant, tenant_id)
            if not tenant or not tenant.admin_phone_numbers:
                return False

            # Remove phone if present
            if normalized_phone in tenant.admin_phone_numbers:
                tenant.admin_phone_numbers.remove(normalized_phone)
                # Mark the field as modified for SQLAlchemy to detect the change
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(tenant, "admin_phone_numbers")
                self.session.commit()
                logger.info(f"Removed admin phone {normalized_phone} from tenant {tenant_id}")

            return True

        except Exception as e:
            logger.error(f"Error removing admin phone {phone_number} from tenant {tenant_id}: {e}")
            self.session.rollback()
            return False

    def list_admin_phones(self, tenant_id: UUID) -> list[str]:
        """
        List all admin phone numbers for a tenant.
        
        Args:
            tenant_id: Tenant ID to list for
            
        Returns:
            List of admin phone numbers
        """
        try:
            from app.db.models import Tenant

            tenant = self.session.get(Tenant, tenant_id)
            if not tenant or not tenant.admin_phone_numbers:
                return []

            return tenant.admin_phone_numbers.copy()

        except Exception as e:
            logger.error(f"Error listing admin phones for tenant {tenant_id}: {e}")
            return []
