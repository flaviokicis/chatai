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
from app.db.session import create_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_dentist_flow() -> dict:
    """Load the dentist flow from fixtures."""
    flow_path = Path(__file__).parent / "tests" / "fixtures" / "dentist_flow.json"
    
    if not flow_path.exists():
        logger.error(f"Dentist flow file not found at: {flow_path}")
        sys.exit(1)
    
    with open(flow_path, "r", encoding="utf-8") as f:
        flow_data = json.load(f)
    
    logger.info("Loaded dentist flow with %d nodes", len(flow_data.get("nodes", [])))
    return flow_data


def load_english_course_flow() -> dict:
    """Load the English course sales flow from playground."""
    flow_path = Path(__file__).parent / "playground" / "english_course_sales_flow.json"

    if not flow_path.exists():
        logger.error(f"English course flow file not found at: {flow_path}")
        sys.exit(1)

    with open(flow_path, "r", encoding="utf-8") as f:
        flow_data = json.load(f)

    logger.info("Loaded english course flow with %d nodes", len(flow_data.get("nodes", [])))
    return flow_data


def create_demo_tenant() -> tuple[UUID, UUID, UUID]:
    """
    Create a demo tenant with dentist configuration.
    
    Returns:
        tuple: (tenant_id, channel_instance_id, flow_id)
    """
    session = create_session()
    
    try:
        # Create tenant with dentist-specific configuration
        logger.info("Creating demo tenant...")
        tenant = create_tenant_with_config(
            session,
            first_name="Dr. Ana",
            last_name="Silva",
            email="ana@clinicadentista.com.br",
            project_description="Clínica odontológica moderna oferecendo tratamentos completos desde limpeza até ortodontia, com foco no atendimento humanizado",
            target_audience="Pacientes de todas as idades que buscam cuidados dentários de qualidade, desde consultas de rotina até procedimentos especializados",
            communication_style="Receptiva calorosa mas profissional de uma clínica dentária brasileira. Tom amigável e acolhedor, mas sempre transmitindo confiança e competência médica. Use linguagem clara e acessível, evitando jargões técnicos desnecessários. Demonstre empatia com possíveis medos ou ansiedades do paciente, seja paciente com dúvidas, e mantenha sempre um tom tranquilizador e positivo."
        )
        
        logger.info(f"Created tenant: {tenant.id}")
        
        # Create WhatsApp channel instance
        logger.info("Creating WhatsApp channel...")
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier="whatsapp:+14155238886",  # Demo WhatsApp number
            phone_number="+14155238886",
            extra={
                "display_name": "Clínica Dra. Ana Silva",
                "business_hours": "Segunda a Sexta: 8h-18h, Sábado: 8h-12h"
            }
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
            definition=flow_definition
        )
        
        logger.info(f"Created flow: {flow.id}")
        
        # Commit all changes
        session.commit()
        
        logger.info("✅ Demo tenant created successfully!")
        logger.info(f"📋 Tenant ID: {tenant.id}")
        logger.info(f"📱 Channel ID: {channel.id}")
        logger.info(f"🌊 Flow ID: {flow.id}")
        logger.info(f"📞 WhatsApp Number: {channel.phone_number}")
        
        return tenant.id, channel.id, flow.id
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Failed to create demo tenant: {e}")
        sys.exit(1)
        
    finally:
        session.close()





def create_english_course_tenant() -> tuple[UUID, UUID, UUID]:
    """
    Create a demo tenant for an English course with its sales flow.

    Returns:
        tuple: (tenant_id, channel_instance_id, flow_id)
    """
    session = create_session()

    try:
        logger.info("Creating english course tenant...")
        tenant = create_tenant_with_config(
            session,
            first_name="Carla",
            last_name="Ferreira",
            email="carla@fluencyacademy.com",
            project_description=(
                "Escola de inglês focada em fluência prática com trilhas para conversação, carreira, viagem e provas."
            ),
            target_audience=(
                "Adultos e jovens que desejam evoluir no inglês para trabalho, viagens e exames."
            ),
            communication_style=(
                "Tom motivador, claro e direto, com foco em resultados práticos. Mensagens curtas, exemplos práticos quando útil, e convite à ação."
            ),
        )

        logger.info(f"Created tenant: {tenant.id}")

        logger.info("Creating WhatsApp channel for english course...")
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier="whatsapp:+14155238887",
            phone_number="+14155238887",
            extra={
                "display_name": "Fluency Academy",
                "business_hours": "Seg-Sex: 9h-19h",
            },
        )

        logger.info(f"Created channel: {channel.id}")

        logger.info("Loading english course flow...")
        flow_definition = load_english_course_flow()

        flow = create_flow(
            session,
            tenant_id=tenant.id,
            channel_instance_id=channel.id,
            name="Vendas Curso de Inglês",
            flow_id="english_course_sales_flow_v1",
            definition=flow_definition,
        )

        logger.info(f"Created flow: {flow.id}")

        session.commit()

        logger.info("✅ English course tenant created successfully!")
        logger.info(f"📋 Tenant ID: {tenant.id}")
        logger.info(f"📱 Channel ID: {channel.id}")
        logger.info(f"🌊 Flow ID: {flow.id}")
        logger.info(f"📞 WhatsApp Number: {channel.phone_number}")

        return tenant.id, channel.id, flow.id

    except Exception as e:
        session.rollback()
        logger.error(f"❌ Failed to create english course tenant: {e}")
        sys.exit(1)

    finally:
        session.close()


def main() -> None:
    """Main seeding function."""
    logger.info("🌱 Starting database seeding...")
    
    # Create or reuse the demo tenant
    tenant_id, channel_id, flow_id = create_demo_tenant()

    # Additionally, attach the english course flow to the same demo tenant/channel
    # so you can switch flows within a single tenant.
    try:
        session = create_session()
        # Reuse the first active tenant (same as --tenant default)
        tenants = get_active_tenants(session)
        demo_tenant = tenants[0]
        channels = get_channel_instances_by_tenant(session, demo_tenant.id)
        channel = channels[0]

        # Only add if it doesn't exist yet
        flows = get_flows_by_tenant(session, demo_tenant.id)
        if not any(f.flow_id == "english_course_sales_flow_v1" for f in flows):
            english_definition = load_english_course_flow()
            flow2 = create_flow(
                session,
                tenant_id=demo_tenant.id,
                channel_instance_id=channel.id,
                name="Vendas Curso de Inglês",
                flow_id="english_course_sales_flow_v1",
                definition=english_definition,
            )
            session.commit()
            logger.info("Added english course flow to demo tenant: %s", flow2.id)
        else:
            logger.info("English course flow already present in demo tenant; skipping add.")
    finally:
        try:
            session.close()
        except Exception:
            pass
    
    logger.info("🎉 Database seeding completed!")
    logger.info("")
    logger.info("Dentist tenant configuration:")
    logger.info(f"  📋 Tenant ID: {tenant_id}")
    logger.info(f"  📱 Channel ID: {channel_id}")
    logger.info(f"  🌊 Flow ID: {flow_id}")
    logger.info(f"  📞 WhatsApp: +14155238886")
    logger.info("")
    logger.info("English course flow also available under the same demo tenant (use --flow-id english_course_sales_flow_v1)")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Configure Twilio webhook to: http://your-domain.com/webhooks/twilio/whatsapp")
    logger.info("2. Test dentist flow with CLI: python -m app.flow_core.cli --tenant default --llm")
    logger.info("3. Test english flow under same tenant with --flow-id:")
    logger.info("   python -m app.flow_core.cli --tenant default --flow-id english_course_sales_flow_v1 --llm")
    logger.info("")
    logger.info("🏥 Dentist clinic and 🎓 English course flow under same tenant are ready!")


if __name__ == "__main__":
    main()