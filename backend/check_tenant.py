#!/usr/bin/env python3
"""
Quick script to check if a tenant exists in the database.
"""

import os
import sys

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def check_tenant(tenant_id: str):
    """Check if a tenant exists by ID."""
    print(f"🔍 Checking for tenant: {tenant_id}")

    try:
        from app.db.models import Tenant
        from app.db.session import create_session

        # Create database session
        db = create_session()

        try:
            # Query for the tenant
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

            if tenant:
                print("✅ Tenant EXISTS:")
                print(f"   ID: {tenant.id}")
                print(f"   Owner: {tenant.owner_first_name} {tenant.owner_last_name}")
                print(f"   Email: {tenant.owner_email}")
                print(f"   Created: {tenant.created_at}")
                print(f"   Updated: {tenant.updated_at}")
                if hasattr(tenant, "admin_phone_numbers"):
                    print(f"   Admin phones: {tenant.admin_phone_numbers}")
                return True
            print(f"❌ Tenant NOT FOUND: {tenant_id}")
            return False
        finally:
            db.close()

    except Exception as e:
        print(f"💥 Error checking tenant: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    tenant_id = "068aace8-3cbf-782f-b0a4-bde1d02ffd6e"
    check_tenant(tenant_id)
