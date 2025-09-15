#!/usr/bin/env python3
"""
Test the exact repository function used by the API.
"""

import os
import sys
from uuid import UUID

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_api_function():
    """Test the exact function used by the admin API."""
    tenant_id = UUID("068b37cd-c090-710d-b0b6-5ca37c2887ff")
    print(f"🔍 Testing get_flows_by_tenant API function for: {tenant_id}")

    try:
        from app.db.repository import get_flows_by_tenant
        from app.db.session import create_session

        # Create database session (same as API)
        db = create_session()

        try:
            # Call the exact function the API uses
            flows = get_flows_by_tenant(db, tenant_id)

            print("📊 API Function Result:")
            print(f"   Function returned: {type(flows)}")
            print(f"   Number of flows: {len(flows) if flows else 0}")

            if flows:
                print(f"✅ Found {len(flows)} flows:")
                for flow in flows:
                    print(f"   - ID: {flow.id}")
                    print(f"     Name: {flow.name}")
                    print(f"     Flow ID: {flow.flow_id}")
                    print(f"     Has definition: {bool(flow.definition)}")
                    print(f"     Created: {flow.created_at}")
                    print()

                # Test the exact API response construction
                print("🔧 Testing API response construction...")
                try:
                    api_responses = []
                    for flow in flows:
                        response_data = {
                            "id": flow.id,
                            "name": flow.name,
                            "flow_id": flow.flow_id,
                            "definition": flow.definition,
                            "created_at": flow.created_at,
                            "updated_at": flow.updated_at,
                            "training_password": getattr(flow, "training_password", None),
                        }
                        api_responses.append(response_data)
                        print(f"   ✅ Successfully created response for: {flow.name}")

                    print(f"✅ All {len(api_responses)} responses created successfully")
                    print("   This suggests the API should work fine...")

                except Exception as e:
                    print(f"💥 Error creating API response: {e}")
                    import traceback

                    traceback.print_exc()

            else:
                print("❌ get_flows_by_tenant returned empty result")
                print("   This explains the 404 error!")

            return flows

        finally:
            db.close()

    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    test_api_function()
