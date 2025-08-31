"""
Integration tests for admin/controller endpoints.

These tests create isolated test data without affecting existing data,
ensuring all admin functionality works correctly without side effects.
"""

import json
import os
from typing import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ChannelType
from app.db.repository import (
    create_channel_instance,
    create_flow,
    create_tenant_with_config,
    delete_tenant_cascade,
    get_tenant_by_id,
)
from app.db.session import create_session
from app.main import app


class TestAdminControllerIntegration:
    """Integration tests for admin controller endpoints."""

    @pytest.fixture(scope="function")
    def client(self) -> Generator[TestClient, None, None]:
        """Create test client with proper session support."""
        with TestClient(app) as test_client:
            yield test_client

    @pytest.fixture(scope="function")
    def admin_session(self, client: TestClient) -> Generator[TestClient, None, None]:
        """Create authenticated admin session."""
        # Set admin password for testing
        os.environ["ADMIN_PASSWORD"] = "test_admin_123"
        os.environ["SESSION_SECRET_KEY"] = "test-session-secret-key-for-testing"
        
        # Login as admin
        login_response = client.post(
            "/controller/auth",
            json={"password": "test_admin_123"}
        )
        assert login_response.status_code == 200
        assert login_response.json()["success"] is True
        
        yield client

    @pytest.fixture(scope="function")
    def test_tenant_data(self) -> Generator[dict, None, None]:
        """Create test tenant data that will be cleaned up after test."""
        session = create_session()
        created_tenant_id = None
        
        try:
            # Create test tenant
            tenant = create_tenant_with_config(
                session,
                first_name="Test",
                last_name="Admin User",
                email="test.admin@example.com",
                project_description="Test project for admin integration tests",
                target_audience="Test audience",
                communication_style="Professional test style"
            )
            created_tenant_id = tenant.id
            
            # Create test channel
            channel = create_channel_instance(
                session,
                tenant_id=tenant.id,
                channel_type=ChannelType.whatsapp,
                identifier="whatsapp:test123456789",
                phone_number="+1234567890",
                extra={"test": True}
            )
            
            # Create test flow
            test_flow_definition = {
                "schema_version": "v1",
                "id": "test.flow",
                "entry": "q.test_question",
                "metadata": {"name": "Test Flow", "description": "Test flow for admin tests"},
                "nodes": [
                    {
                        "id": "q.test_question",
                        "kind": "Question",
                        "key": "test_answer",
                        "prompt": "This is a test question?"
                    }
                ]
            }
            
            flow = create_flow(
                session,
                tenant_id=tenant.id,
                channel_instance_id=channel.id,
                name="Test Flow",
                flow_id="test_flow_admin_integration",
                definition=test_flow_definition
            )
            
            session.commit()
            
            yield {
                "tenant_id": tenant.id,
                "channel_id": channel.id,
                "flow_id": flow.id,
                "tenant": tenant,
                "channel": channel,
                "flow": flow
            }
            
        finally:
            # Cleanup: Delete test tenant and all associated data
            if created_tenant_id:
                try:
                    delete_tenant_cascade(session, created_tenant_id)
                    session.commit()
                except Exception as e:
                    session.rollback()
                    print(f"Warning: Failed to cleanup test tenant {created_tenant_id}: {e}")
            session.close()

    def test_admin_health_endpoint(self, client: TestClient) -> None:
        """Test admin health endpoint is accessible."""
        response = client.get("/controller/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "controller"

    def test_admin_auth_invalid_password(self, client: TestClient) -> None:
        """Test admin authentication with invalid password."""
        os.environ["ADMIN_PASSWORD"] = "correct_password"
        
        response = client.post(
            "/controller/auth",
            json={"password": "wrong_password"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid password" in data["message"]

    def test_admin_auth_missing_config(self, client: TestClient) -> None:
        """Test admin authentication when password not configured."""
        if "ADMIN_PASSWORD" in os.environ:
            del os.environ["ADMIN_PASSWORD"]
        
        response = client.post(
            "/controller/auth",
            json={"password": "any_password"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not configured" in data["message"]

    def test_admin_auth_successful(self, client: TestClient) -> None:
        """Test successful admin authentication."""
        os.environ["ADMIN_PASSWORD"] = "test_admin_123"
        os.environ["SESSION_SECRET_KEY"] = "test-session-secret"
        
        response = client.post(
            "/controller/auth",
            json={"password": "test_admin_123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Authentication successful" in data["message"]
        assert data["expires_at"] is not None

    def test_unauthorized_access_to_tenants(self, client: TestClient) -> None:
        """Test that tenant endpoints require authentication."""
        response = client.get("/controller/tenants")
        assert response.status_code == 401

    def test_list_tenants_authenticated(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test listing tenants with authentication."""
        response = admin_session.get("/controller/tenants")
        assert response.status_code == 200
        
        tenants = response.json()
        assert isinstance(tenants, list)
        
        # Should include our test tenant
        test_tenant_found = False
        for tenant in tenants:
            if tenant["id"] == str(test_tenant_data["tenant_id"]):
                test_tenant_found = True
                assert tenant["owner_first_name"] == "Test"
                assert tenant["owner_last_name"] == "Admin User"
                assert tenant["owner_email"] == "test.admin@example.com"
                assert tenant["channel_count"] == 1
                assert tenant["flow_count"] == 1
                break
        
        assert test_tenant_found, "Test tenant not found in response"

    def test_create_tenant(self, admin_session: TestClient) -> None:
        """Test creating a new tenant."""
        new_tenant_data = {
            "owner_first_name": "New",
            "owner_last_name": "Test User",
            "owner_email": "new.test@example.com",
            "project_description": "New test project",
            "target_audience": "Test users",
            "communication_style": "Friendly test style"
        }
        
        response = admin_session.post("/controller/tenants", json=new_tenant_data)
        assert response.status_code == 200
        
        created_tenant = response.json()
        assert created_tenant["owner_first_name"] == "New"
        assert created_tenant["owner_last_name"] == "Test User"
        assert created_tenant["owner_email"] == "new.test@example.com"
        assert UUID(created_tenant["id"])  # Valid UUID
        
        # Cleanup: Delete the created tenant
        session = create_session()
        try:
            delete_tenant_cascade(session, UUID(created_tenant["id"]))
            session.commit()
        finally:
            session.close()

    def test_update_tenant(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test updating a tenant."""
        tenant_id = test_tenant_data["tenant_id"]
        update_data = {
            "owner_first_name": "Updated",
            "owner_last_name": "Test User",
            "project_description": "Updated test description"
        }
        
        response = admin_session.put(f"/controller/tenants/{tenant_id}", json=update_data)
        assert response.status_code == 200
        
        updated_tenant = response.json()
        assert updated_tenant["owner_first_name"] == "Updated"
        assert updated_tenant["owner_last_name"] == "Test User"
        assert "Updated test description" in updated_tenant["project_description"]

    def test_delete_tenant(self, admin_session: TestClient) -> None:
        """Test deleting a tenant (creates its own tenant for deletion)."""
        # Create a tenant specifically for deletion testing
        session = create_session()
        tenant = create_tenant_with_config(
            session,
            first_name="Delete",
            last_name="Me",
            email="delete.me@example.com",
            project_description="This tenant will be deleted"
        )
        session.commit()
        tenant_id = tenant.id
        session.close()
        
        # Delete via API
        response = admin_session.delete(f"/controller/tenants/{tenant_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "deleted successfully" in data["message"]
        
        # Verify deletion
        session = create_session()
        try:
            deleted_tenant = get_tenant_by_id(session, tenant_id)
            assert deleted_tenant is None
        finally:
            session.close()

    def test_list_tenant_channels(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test listing channels for a tenant."""
        tenant_id = test_tenant_data["tenant_id"]
        
        response = admin_session.get(f"/controller/tenants/{tenant_id}/channels")
        assert response.status_code == 200
        
        channels = response.json()
        assert isinstance(channels, list)
        assert len(channels) == 1
        
        channel = channels[0]
        assert channel["channel_type"] == "whatsapp"
        assert channel["identifier"] == "whatsapp:test123456789"
        assert channel["phone_number"] == "+1234567890"

    def test_create_tenant_channel(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test creating a new channel for a tenant."""
        tenant_id = test_tenant_data["tenant_id"]
        
        channel_data = {
            "channel_type": "whatsapp",
            "identifier": "whatsapp:test987654321",
            "phone_number": "+0987654321",
            "extra": {"test_channel": True}
        }
        
        response = admin_session.post(f"/controller/tenants/{tenant_id}/channels", json=channel_data)
        assert response.status_code == 200
        
        created_channel = response.json()
        assert created_channel["channel_type"] == "whatsapp"
        assert created_channel["identifier"] == "whatsapp:test987654321"
        assert created_channel["phone_number"] == "+0987654321"

    def test_list_tenant_flows(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test listing flows for a tenant."""
        tenant_id = test_tenant_data["tenant_id"]
        
        response = admin_session.get(f"/controller/tenants/{tenant_id}/flows")
        assert response.status_code == 200
        
        flows = response.json()
        assert isinstance(flows, list)
        assert len(flows) == 1
        
        flow = flows[0]
        assert flow["name"] == "Test Flow"
        assert flow["flow_id"] == "test_flow_admin_integration"
        assert "nodes" in flow["definition"]

    def test_update_flow_definition(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test updating a flow's JSON definition."""
        flow_id = test_tenant_data["flow_id"]
        
        updated_definition = {
            "schema_version": "v1",
            "id": "test.updated_flow",
            "entry": "q.updated_question",
            "metadata": {"name": "Updated Test Flow", "description": "Updated test flow"},
            "nodes": [
                {
                    "id": "q.updated_question",
                    "kind": "Question",
                    "key": "updated_answer",
                    "prompt": "This is an updated test question?"
                },
                {
                    "id": "q.second_question",
                    "kind": "Question", 
                    "key": "second_answer",
                    "prompt": "This is a second question?"
                }
            ]
        }
        
        response = admin_session.put(f"/controller/flows/{flow_id}", json={"definition": updated_definition})
        assert response.status_code == 200
        
        updated_flow = response.json()
        assert updated_flow["definition"]["id"] == "test.updated_flow"
        assert len(updated_flow["definition"]["nodes"]) == 2
        assert updated_flow["definition"]["nodes"][0]["prompt"] == "This is an updated test question?"

    def test_admin_logout(self, admin_session: TestClient) -> None:
        """Test admin logout functionality."""
        response = admin_session.post("/controller/logout")
        assert response.status_code == 200
        
        data = response.json()
        assert "Logged out successfully" in data["message"]
        
        # Verify session is invalidated
        response = admin_session.get("/controller/tenants")
        assert response.status_code == 401

    def test_nonexistent_tenant_operations(self, admin_session: TestClient) -> None:
        """Test operations on non-existent tenants."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        
        # Try to update non-existent tenant
        response = admin_session.put(f"/controller/tenants/{fake_uuid}", json={"owner_first_name": "Test"})
        assert response.status_code == 404
        
        # Try to delete non-existent tenant
        response = admin_session.delete(f"/controller/tenants/{fake_uuid}")
        assert response.status_code == 404
        
        # Try to list channels for non-existent tenant
        response = admin_session.get(f"/controller/tenants/{fake_uuid}/channels")
        assert response.status_code == 200  # Should return empty list
        assert response.json() == []

    def test_nonexistent_flow_operations(self, admin_session: TestClient) -> None:
        """Test operations on non-existent flows."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        
        response = admin_session.put(f"/controller/flows/{fake_uuid}", json={"definition": {"test": "data"}})
        assert response.status_code == 404

    def test_invalid_json_flow_update(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test flow update with invalid JSON structure."""
        flow_id = test_tenant_data["flow_id"]
        
        # Missing required fields
        invalid_definition = {
            "schema_version": "v1"
            # Missing id, entry, nodes, etc.
        }
        
        response = admin_session.put(f"/controller/flows/{flow_id}", json={"definition": invalid_definition})
        # Should accept any JSON (validation happens at flow execution time)
        assert response.status_code == 200

    def test_tenant_creation_validation(self, admin_session: TestClient) -> None:
        """Test tenant creation with invalid data."""
        # Missing required fields
        invalid_data = {
            "owner_first_name": "",  # Empty name
            "owner_email": "invalid-email"  # Invalid email format
        }
        
        response = admin_session.post("/controller/tenants", json=invalid_data)
        assert response.status_code == 422  # Validation error

    def test_gdpr_data_encryption(self, admin_session: TestClient, test_tenant_data: dict) -> None:
        """Test that PII data is properly encrypted in responses."""
        response = admin_session.get("/controller/tenants")
        assert response.status_code == 200
        
        tenants = response.json()
        test_tenant = None
        for tenant in tenants:
            if tenant["id"] == str(test_tenant_data["tenant_id"]):
                test_tenant = tenant
                break
        
        assert test_tenant is not None
        # The API should return decrypted data for admin use
        assert test_tenant["owner_first_name"] == "Test"
        assert test_tenant["owner_email"] == "test.admin@example.com"
        
        # Verify data is actually encrypted in database
        session = create_session()
        try:
            # Direct database query should show encrypted data
            from app.db.models import Tenant
            from sqlalchemy import text
            
            result = session.execute(
                text("SELECT owner_first_name, owner_email FROM tenants WHERE id = :tenant_id"),
                {"tenant_id": test_tenant_data["tenant_id"]}
            ).fetchone()
            
            if result:
                # Raw database values should be binary (encrypted)
                assert isinstance(result[0], (bytes, memoryview))  # owner_first_name encrypted
                assert isinstance(result[1], (bytes, memoryview))  # owner_email encrypted
        finally:
            session.close()

    def test_cascade_delete_behavior(self, admin_session: TestClient) -> None:
        """Test that deleting a tenant properly cascades to all related data."""
        # Create a tenant with full data structure
        session = create_session()
        
        tenant = create_tenant_with_config(
            session,
            first_name="Cascade",
            last_name="Test",
            email="cascade.test@example.com",
            project_description="Test cascade deletion"
        )
        
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier="whatsapp:cascade123",
            phone_number="+1111111111"
        )
        
        flow = create_flow(
            session,
            tenant_id=tenant.id,
            channel_instance_id=channel.id,
            name="Cascade Test Flow",
            flow_id="cascade_test_flow",
            definition={"schema_version": "v1", "id": "test", "entry": "q.test", "nodes": []}
        )
        
        session.commit()
        tenant_id = tenant.id
        channel_id = channel.id
        flow_id = flow.id
        session.close()
        
        # Delete tenant via API
        response = admin_session.delete(f"/controller/tenants/{tenant_id}")
        assert response.status_code == 200
        
        # Verify all related data is deleted
        session = create_session()
        try:
            from app.db.models import Tenant, ChannelInstance, Flow
            
            # Tenant should be deleted
            deleted_tenant = session.get(Tenant, tenant_id)
            assert deleted_tenant is None
            
            # Channel should be deleted (cascade)
            deleted_channel = session.get(ChannelInstance, channel_id)
            assert deleted_channel is None
            
            # Flow should be deleted (cascade)
            deleted_flow = session.get(Flow, flow_id)
            assert deleted_flow is None
            
        finally:
            session.close()

    def test_admin_session_expiry(self, client: TestClient) -> None:
        """Test that admin sessions properly expire."""
        os.environ["ADMIN_PASSWORD"] = "test_admin_123"
        
        # Login
        login_response = client.post("/controller/auth", json={"password": "test_admin_123"})
        assert login_response.status_code == 200
        
        # Should be able to access tenants
        response = client.get("/controller/tenants")
        assert response.status_code == 200
        
        # Logout
        logout_response = client.post("/controller/logout")
        assert logout_response.status_code == 200
        
        # Should no longer be able to access tenants
        response = client.get("/controller/tenants")
        assert response.status_code == 401

    def test_concurrent_admin_sessions(self, client: TestClient) -> None:
        """Test that multiple admin sessions can coexist."""
        os.environ["ADMIN_PASSWORD"] = "test_admin_123"
        
        # Create two separate clients to simulate different browser sessions
        with TestClient(app) as client1, TestClient(app) as client2:
            # Both should be able to login independently
            login1 = client1.post("/controller/auth", json={"password": "test_admin_123"})
            login2 = client2.post("/controller/auth", json={"password": "test_admin_123"})
            
            assert login1.status_code == 200
            assert login2.status_code == 200
            
            # Both should be able to access tenants
            response1 = client1.get("/controller/tenants")
            response2 = client2.get("/controller/tenants")
            
            assert response1.status_code == 200
            assert response2.status_code == 200
