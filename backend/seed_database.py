#!/usr/bin/env python3
"""
Database seeding script for ChatAI backend.

This script creates initial data including:
- Default tenant with project configuration
- Channel instance (WhatsApp number)
- Flow definition from flow_example.json
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.db.repository import (
    create_channel_instance,
    create_flow,
    create_tenant_with_config,
    get_active_tenants,
    get_channel_instances_by_tenant,
    get_flows_by_tenant,
)
from app.db.session import create_session

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default tenant configuration
DEFAULT_TENANT_CONFIG = {
    "first_name": "ChatAI",
    "last_name": "Demo",
    "email": "demo@chatai.com",
    "project_description": "Empresa de iluminação esportiva especializada em soluções LED para quadras, campos e galpões",
    "target_audience": "Empresários e gestores de espaços esportivos, construtoras e arquitetos que buscam soluções de iluminação profissional",
    "communication_style": "Profissional mas acessível, focado em soluções técnicas e benefícios práticos. Use linguagem clara e direta.",
}

# Default channel configuration
DEFAULT_CHANNEL_CONFIG = {
    "channel_type": "whatsapp",
    "identifier": "whatsapp:+5511999999999",  # Demo WhatsApp number
    "phone_number": "+5511999999999",
    "extra": {
        "description": "Demo WhatsApp channel for testing",
        "webhook_url": "http://localhost:8000/webhooks/twilio/whatsapp",
    },
}


def load_flow_example() -> dict[str, Any]:
    """Load the example flow from playground directory."""
    flow_path = Path(__file__).parent / "playground" / "flow_example.json"

    if not flow_path.exists():
        raise FileNotFoundError(f"Flow example not found at: {flow_path}")

    with flow_path.open() as f:
        flow_data = json.load(f)

    logger.info(f"Loaded flow example: {flow_data['id']}")
    return flow_data


def create_or_get_default_tenant(session):
    """Create or get the default tenant for seeding."""
    # Check if any tenants exist
    tenants = get_active_tenants(session)

    if tenants:
        tenant = tenants[0]  # Use first tenant
        logger.info(f"Using existing tenant: {tenant.id} ({tenant.owner_email})")
        return tenant

    # Create new tenant
    logger.info("Creating default tenant...")
    tenant = create_tenant_with_config(session, **DEFAULT_TENANT_CONFIG)
    session.commit()
    logger.info(f"Created tenant: {tenant.id} ({tenant.owner_email})")
    return tenant


def create_or_get_channel_instance(session, tenant_id):
    """Create or get a channel instance for the tenant."""
    # Check if tenant already has channels
    channels = get_channel_instances_by_tenant(session, tenant_id)

    if channels:
        channel = channels[0]  # Use first channel
        logger.info(f"Using existing channel: {channel.identifier}")
        return channel

    # Create new channel
    logger.info("Creating default channel instance...")
    channel = create_channel_instance(
        session,
        tenant_id=tenant_id,
        channel_type=DEFAULT_CHANNEL_CONFIG["channel_type"],
        identifier=DEFAULT_CHANNEL_CONFIG["identifier"],
        phone_number=DEFAULT_CHANNEL_CONFIG["phone_number"],
        extra=DEFAULT_CHANNEL_CONFIG["extra"],
    )
    session.commit()
    logger.info(f"Created channel: {channel.identifier}")
    return channel


def create_example_flow(session, tenant_id, channel_instance_id, flow_data):
    """Create the example flow in the database."""
    # Check if flow already exists
    flows = get_flows_by_tenant(session, tenant_id)
    existing_flow = next((f for f in flows if f.flow_id == flow_data["id"]), None)

    if existing_flow:
        logger.info(f"Flow already exists: {existing_flow.flow_id}")
        return existing_flow

    # Create new flow
    logger.info(f"Creating flow: {flow_data['id']}")
    flow = create_flow(
        session,
        tenant_id=tenant_id,
        channel_instance_id=channel_instance_id,
        name="Exemplo de Vendas - Iluminação Esportiva",
        flow_id=flow_data["id"],
        definition=flow_data,
    )
    session.commit()
    logger.info(f"Created flow: {flow.flow_id} (DB ID: {flow.id})")
    return flow


def seed_database():
    """Main seeding function."""
    logger.info("🌱 Starting database seeding...")

    try:
        # Load flow example
        flow_data = load_flow_example()

        # Create database session
        session = create_session()

        try:
            # 1. Create or get tenant
            tenant = create_or_get_default_tenant(session)

            # 2. Create or get channel instance
            channel = create_or_get_channel_instance(session, tenant.id)

            # 3. Create example flow
            flow = create_example_flow(session, tenant.id, channel.id, flow_data)

            # Final commit
            session.commit()

            logger.info("✅ Database seeding completed successfully!")
            logger.info(f"   Tenant ID: {tenant.id}")
            logger.info(f"   Channel ID: {channel.id} ({channel.identifier})")
            logger.info(f"   Flow ID: {flow.id} ({flow.flow_id})")

            print("\n🎉 Seeding Summary:")
            print(
                f"   • Tenant: {tenant.owner_first_name} {tenant.owner_last_name} ({tenant.owner_email})"
            )
            print(f"   • Channel: {channel.identifier}")
            print(f"   • Flow: {flow.name}")
            print(
                f"\n💡 You can now test the WhatsApp bot by sending messages to: {channel.phone_number}"
            )
            print(f"   The frontend will automatically use tenant ID: {tenant.id}")

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    seed_database()
