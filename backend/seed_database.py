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
from app.db.repository import create_channel_instance, create_flow, create_tenant_with_config
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





def main() -> None:
    """Main seeding function."""
    logger.info("🌱 Starting database seeding...")
    
    # Create the demo tenant
    tenant_id, channel_id, flow_id = create_demo_tenant()
    
    logger.info("🎉 Database seeding completed!")
    logger.info("")
    logger.info("Demo tenant configuration:")
    logger.info(f"  📋 Tenant ID: {tenant_id}")
    logger.info(f"  📱 Channel ID: {channel_id}")
    logger.info(f"  🌊 Flow ID: {flow_id}")
    logger.info(f"  📞 WhatsApp: +14155238886")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Configure Twilio webhook to: http://your-domain.com/webhooks/twilio/whatsapp")
    logger.info("2. Test with CLI: python -m app.flow_core.cli --tenant default --llm")
    logger.info("3. Or test via WhatsApp messages to +14155238886")
    logger.info("")
    logger.info("🏥 Dr. Ana Silva's dental clinic is ready to receive patients!")


if __name__ == "__main__":
    main()