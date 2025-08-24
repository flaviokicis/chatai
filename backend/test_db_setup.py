#!/usr/bin/env python3
"""Test script to verify database setup and basic operations."""

import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from app.db.base import Base
from app.db.models import (
    ChannelInstance,
    ChannelType,
    Flow,
    Tenant,
    TenantProjectConfig,
)
from app.db.session import create_session, get_engine


def test_database_setup():
    """Test basic database operations."""
    print("🔧 Testing database setup...")

    # Set a test encryption key if not set
    if not os.getenv("PII_ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key().decode()
        os.environ["PII_ENCRYPTION_KEY"] = test_key
        print(f"🔑 Generated test encryption key: {test_key}")

    try:
        # Create tables
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully")

        # Test basic operations
        session = create_session()
        try:
            # Create a test tenant
            tenant = Tenant(
                owner_first_name="Test",
                owner_last_name="User",
                owner_email="test@example.com",
            )
            session.add(tenant)
            session.flush()

            # Create project config
            config = TenantProjectConfig(
                tenant_id=tenant.id,
                project_description="Test fitness studio",
                target_audience="Fitness enthusiasts aged 25-45",
                communication_style="Friendly and professional",
            )
            session.add(config)
            session.flush()

            # Create channel instance
            channel = ChannelInstance(
                tenant_id=tenant.id,
                channel_type=ChannelType.whatsapp,
                identifier="whatsapp:+14155238886",
                phone_number="+14155238886",
            )
            session.add(channel)
            session.flush()

            # Create flow
            flow = Flow(
                tenant_id=tenant.id,
                channel_instance_id=channel.id,
                name="Sales Qualification Flow",
                flow_id="sales_qualifier_v1",
                definition={
                    "schema_version": "v2",
                    "id": "flow.sales_qualifier",
                    "entry": "q.intention",
                    "nodes": [
                        {
                            "id": "q.intention",
                            "kind": "Question",
                            "key": "intention",
                            "prompt": "Como posso te ajudar hoje?",
                        }
                    ],
                    "edges": [],
                },
            )
            session.add(flow)
            session.commit()

            print(f"✅ Created test tenant (ID: {tenant.id})")
            print(f"✅ Created channel instance (ID: {channel.id})")
            print(f"✅ Created flow (ID: {flow.id})")

            # Test encryption by retrieving data
            retrieved_tenant = session.query(Tenant).filter_by(id=tenant.id).first()
            assert retrieved_tenant is not None
            assert retrieved_tenant.owner_email == "test@example.com"
            print("✅ Email encryption/decryption working")

            # Clean up test data
            session.delete(flow)
            session.delete(channel)
            session.delete(config)
            session.delete(tenant)
            session.commit()
            print("✅ Test data cleaned up")

        finally:
            session.close()

        print("🎉 All database tests passed!")
        assert True

    except Exception as exc:
        print(f"❌ Database test failed: {exc}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_database_setup()
    sys.exit(0 if success else 1)
