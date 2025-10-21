#!/usr/bin/env python3
"""
Database seeding script for ChatAI.

This script creates a demo tenant with the dentist flow configured for testing purposes.
It sets up tenant, channel, and flow data in the database for webhook and CLI testing.
"""

import json
import logging
import sys
from pathlib import Path
from uuid import UUID

from app.db.models import ChannelType
from app.db.repository import (
    create_channel_instance,
    create_flow,
    create_tenant_with_config,
    get_active_tenants,
    get_channel_instances_by_tenant,
    get_flows_by_tenant,
)
from app.db.session import db_transaction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_dentist_flow() -> dict:
    """Load the dentist flow from fixtures."""
    flow_path = Path(__file__).parent / "tests" / "fixtures" / "dentist_flow.json"

    if not flow_path.exists():
        logger.error(f"Dentist flow file not found at: {flow_path}")
        sys.exit(1)

    with open(flow_path, encoding="utf-8") as f:
        flow_data = json.load(f)

    logger.info("Loaded dentist flow with %d nodes", len(flow_data.get("nodes", [])))
    return flow_data


def load_english_course_flow() -> dict:
    """Load the English course sales flow from playground."""
    flow_path = Path(__file__).parent / "playground" / "english_course_sales_flow.json"

    if not flow_path.exists():
        logger.error(f"English course flow file not found at: {flow_path}")
        sys.exit(1)

    with open(flow_path, encoding="utf-8") as f:
        flow_data = json.load(f)

    logger.info("Loaded english course flow with %d nodes", len(flow_data.get("nodes", [])))
    return flow_data


def get_or_create_demo_tenant() -> tuple[UUID, UUID, UUID]:
    """
    Get existing tenant or create a demo tenant with dentist configuration.

    Returns:
        tuple: (tenant_id, channel_instance_id, flow_id)
    """
    with db_transaction() as session:
        # Check if there are existing active tenants
        logger.info("Checking for existing tenants...")
        existing_tenants = get_active_tenants(session)

        if existing_tenants:
            # Use the first existing tenant
            tenant = existing_tenants[0]
            logger.info(
                f"Using existing tenant: {tenant.id} ({tenant.owner_first_name} {tenant.owner_last_name})"
            )

            # Get existing channel
            channels = get_channel_instances_by_tenant(session, tenant.id)
            if not channels:
                logger.error(
                    "❌ Existing tenant has no channels. Please create one manually or delete the tenant."
                )
                sys.exit(1)

            channel = channels[0]
            logger.info(f"Using existing channel: {channel.id}")

            # Check if dentist flow already exists
            flows = get_flows_by_tenant(session, tenant.id)
            dentist_flow = None
            for flow in flows:
                if flow.flow_id == "dentist_consultation_flow_v1":
                    dentist_flow = flow
                    break

            if not dentist_flow:
                # Create the dentist flow
                logger.info("Creating dentist flow for existing tenant...")
                flow_definition = load_dentist_flow()

                dentist_flow = create_flow(
                    session,
                    tenant_id=tenant.id,
                    channel_instance_id=channel.id,
                    name="Atendimento Consultório Dentista",
                    flow_id="dentist_consultation_flow_v1",
                    definition=flow_definition,
                )
                session.commit()
                logger.info(f"Created dentist flow: {dentist_flow.id}")
            else:
                logger.info(f"Using existing dentist flow: {dentist_flow.id}")

            return tenant.id, channel.id, dentist_flow.id

        # Create new tenant with dentist-specific configuration
        logger.info("No existing tenants found. Creating demo tenant...")
        tenant = create_tenant_with_config(
            session,
            first_name="Dr. Ana",
            last_name="Silva",
            email="ana@clinicadentista.com.br",
            project_description="Clínica odontológica moderna oferecendo tratamentos completos desde limpeza até ortodontia, com foco no atendimento humanizado",
            target_audience="Pacientes de todas as idades que buscam cuidados dentários de qualidade, desde consultas de rotina até procedimentos especializados",
            communication_style="Receptiva calorosa mas profissional de uma clínica dentária brasileira. Tom amigável e acolhedor, mas sempre transmitindo confiança e competência médica. Use linguagem clara e acessível, evitando jargões técnicos desnecessários. Demonstre empatia com possíveis medos ou ansiedades do paciente, seja paciente com dúvidas, e mantenha sempre um tom tranquilizador e positivo.",
        )

        logger.info(f"Created tenant: {tenant.id}")

        # Create WhatsApp channel instance
        logger.info("Creating WhatsApp channel...")
        # Note: Phone Number ID (674436192430525) is WhatsApp Cloud API specific identifier
        # It's different from the actual phone number (+15550489424) and is what webhooks receive
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier="whatsapp:674436192430525",  # WhatsApp Cloud API Phone Number ID
            phone_number="+15550489424",  # Actual display phone number
            extra={
                "display_name": "Clínica Dra. Ana Silva",
                "business_hours": "Segunda a Sexta: 8h-18h, Sábado: 8h-12h",
            },
        )

        logger.info(f"Created channel: {channel.id}")

        # Load and create the dentist flow
        logger.info("Loading dentist flow...")
        flow_definition = load_dentist_flow()

        flow = create_flow(
            session,
            tenant_id=tenant.id,
            channel_instance_id=channel.id,
            name="Atendimento Consultório Dentista",
            flow_id="dentist_consultation_flow_v1",
            definition=flow_definition,
        )

        logger.info(f"Created flow: {flow.id}")

        # Auto-commit happens here with db_transaction context manager
        logger.info("✅ Demo tenant created successfully!")
        logger.info(f"📋 Tenant ID: {tenant.id}")
        logger.info(f"📱 Channel ID: {channel.id}")
        logger.info(f"🌊 Flow ID: {flow.id}")
        logger.info(f"📞 WhatsApp Number: {channel.phone_number}")

        return tenant.id, channel.id, flow.id


def main() -> None:
    """Main seeding function."""
    logger.info("🌱 Starting database seeding...")

    # Get or create the demo tenant
    tenant_id, channel_id, dentist_flow_id = get_or_create_demo_tenant()

    # Ensure the English course flow also exists on the same tenant
    try:
        with db_transaction() as session:
            flows = get_flows_by_tenant(session, tenant_id)
            if not any(f.flow_id == "english_course_sales_flow_v1" for f in flows):
                logger.info("Adding English course flow to tenant...")
                english_definition = load_english_course_flow()
                english_flow = create_flow(
                    session,
                    tenant_id=tenant_id,
                    channel_instance_id=channel_id,
                    name="Vendas Curso de Inglês",
                    flow_id="english_course_sales_flow_v1",
                    definition=english_definition,
                )
                # Auto-commit happens here
                logger.info(f"Added English course flow: {english_flow.id}")
            else:
                logger.info("English course flow already exists on tenant")
    except Exception as e:
        logger.error(f"❌ Failed to add English course flow: {e}")

    logger.info("🎉 Database seeding completed!")
    logger.info("")
    logger.info("Tenant configuration:")
    logger.info(f"  📋 Tenant ID: {tenant_id}")
    logger.info(f"  📱 Channel ID: {channel_id}")
    logger.info(f"  🌊 Dentist Flow ID: {dentist_flow_id}")
    logger.info("")
    logger.info("Available flows:")
    logger.info("  🏥 Dentist consultation: dentist_consultation_flow_v1")
    logger.info("  🎓 English course sales: english_course_sales_flow_v1")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Configure Twilio webhook to: http://your-domain.com/webhooks/twilio/whatsapp")
    logger.info("2. Test dentist flow with CLI: python -m app.flow_core.cli --tenant default --llm")
    logger.info(
        "3. Test English flow with CLI: python -m app.flow_core.cli --tenant default --flow-id english_course_sales_flow_v1 --llm"
    )
    logger.info("")
    logger.info("✅ Both flows are ready on your existing tenant!")


if __name__ == "__main__":
    main()
