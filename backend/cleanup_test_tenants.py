#!/usr/bin/env python3
"""
Script to clean up test tenants from the database.
Keeps only GlixLeds Iluminate and deletes all Test User tenants.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))


from app.db.models import ChannelInstance, Tenant
from app.db.session import db_session


def cleanup_test_tenants():
    """Delete all test tenants except GlixLeds."""
    with db_session() as session:
        # Find all tenants
        tenants = session.query(Tenant).all()
        
        deleted_count = 0
        kept_count = 0
        
        print("🔍 Found tenants:")
        for tenant in tenants:
            tenant_name = f"{tenant.owner_first_name} {tenant.owner_last_name}"
            print(f"  • {tenant_name} ({tenant.owner_email})")
            
            # Check if this is a test tenant
            if (tenant.owner_first_name == "Test" and tenant.owner_last_name == "User") or \
               (tenant.owner_first_name == "Schema" and tenant.owner_last_name == "Test") or \
               (tenant.owner_first_name == "CLI" and tenant.owner_last_name == "Test"):
                # Delete test tenant (cascade will delete channels, flows, etc.)
                session.delete(tenant)
                deleted_count += 1
                print("    ❌ Marked for deletion")
            else:
                kept_count += 1
                print("    ✅ Keeping")
        
        # Show channels for remaining tenants
        print("\n📱 Channels that will remain:")
        remaining_channels = session.query(ChannelInstance).join(Tenant).filter(
            ~((Tenant.owner_first_name == "Test") & (Tenant.owner_last_name == "User")) &
            ~((Tenant.owner_first_name == "Schema") & (Tenant.owner_last_name == "Test")) &
            ~((Tenant.owner_first_name == "CLI") & (Tenant.owner_last_name == "Test"))
        ).all()
        
        for channel in remaining_channels:
            tenant_name = f"{channel.tenant.owner_first_name} {channel.tenant.owner_last_name}"
            print(f"  • {channel.identifier} (Tenant: {tenant_name})")
        
        # Confirm before committing
        print(f"\n⚠️  About to delete {deleted_count} test tenants and keep {kept_count} real tenants.")
        response = input("Proceed? (yes/no): ")
        
        if response.lower() == "yes":
            session.commit()
            print(f"✅ Deleted {deleted_count} test tenants")
        else:
            session.rollback()
            print("❌ Cancelled - no changes made")

if __name__ == "__main__":
    cleanup_test_tenants()
