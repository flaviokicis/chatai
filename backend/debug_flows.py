#!/usr/bin/env python3
"""
Debug script to check tenant and flows.
"""

import os
import sys

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def debug_tenant_and_flows(tenant_id: str):
    """Debug tenant and associated flows."""
    print(f"🔍 Debugging tenant and flows: {tenant_id}")

    try:
        from app.db.models import Flow, Tenant
        from app.db.session import create_session

        # Create database session
        db = create_session()

        try:
            # Check if tenant exists
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

            if not tenant:
                print(f"❌ Tenant NOT FOUND: {tenant_id}")
                return None

            print("✅ Tenant EXISTS:")
            print(f"   ID: {tenant.id}")
            print(f"   Owner: {tenant.owner_first_name} {tenant.owner_last_name}")
            print(f"   Email: {tenant.owner_email}")
            print(f"   Created: {tenant.created_at}")

            # Check for flows (all flows)
            print("\n🔍 Checking ALL flows for tenant...")
            all_flows = db.query(Flow).filter(Flow.tenant_id == tenant_id).all()

            # Check for active flows (not deleted)
            print("🔍 Checking ACTIVE flows for tenant...")
            active_flows = (
                db.query(Flow).filter(Flow.tenant_id == tenant_id, Flow.deleted_at.is_(None)).all()
            )

            print("📊 Flow Summary:")
            print(f"   Total flows: {len(all_flows)}")
            print(f"   Active flows: {len(active_flows)}")

            if all_flows:
                print(f"\n✅ Found {len(all_flows)} total flows:")
                for flow in all_flows:
                    deleted_status = "DELETED" if flow.deleted_at else "ACTIVE"
                    print(f"   - ID: {flow.id}")
                    print(f"     Name: {flow.name}")
                    print(f"     Status: {deleted_status}")
                    print(f"     Created: {flow.created_at}")
                    if flow.deleted_at:
                        print(f"     Deleted: {flow.deleted_at}")
                    print()

                if len(active_flows) == 0:
                    print("❌ ALL FLOWS ARE DELETED!")
                    print("   This explains the 404 error - flows exist but are marked as deleted.")
            else:
                print(f"❌ NO FLOWS found for tenant {tenant_id}")
                print("   This explains the 404 error - the tenant exists but has no flows.")

            return len(active_flows) if active_flows else 0

        finally:
            db.close()

    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    # The tenant ID from the logs
    tenant_id = "068b37cd-c090-710d-b0b6-5ca37c2887ff"
    debug_tenant_and_flows(tenant_id)
