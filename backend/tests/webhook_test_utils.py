"""Shared utilities for webhook testing with database-driven approach."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.session import create_session
from app.db.repository import (
    create_tenant_with_config,
    create_channel_instance, 
    create_flow,
)
from app.db.models import ChannelType


def _patch_signature_validation(monkeypatch):
    """Bypass Twilio signature validation in tests."""
    from app.whatsapp.twilio_adapter import TwilioWhatsAppAdapter

    async def _ok(_self, request, _sig):
        form = await request.form()
        return {k: str(v) for k, v in form.items()}

    monkeypatch.setattr(TwilioWhatsAppAdapter, "validate_and_parse", _ok)


def create_test_tenant_with_flow(
    flow_definition: dict[str, Any] | None = None,
    tenant_name: str = "Test",
    channel_number: str | None = None,
    flow_name: str = "Test Flow"
) -> tuple[Any, Any, Any, str]:
    """
    Create a test tenant with flow in database.
    
    Returns:
        tuple: (tenant, channel_instance, flow, channel_number)
    """
    test_id = str(uuid.uuid4())[:8]
    
    session = create_session()
    
    try:
        # Create tenant
        tenant = create_tenant_with_config(
            session,
            first_name=tenant_name,
            last_name="User", 
            email=f"test-{test_id}@example.com",
            project_description="Test project",
            target_audience="Test audience",
            communication_style="Test style"
        )
        
        # Create WhatsApp channel with unique number if not provided
        if channel_number is None:
            channel_number = f"whatsapp:+1555{test_id[:4]}{test_id[4:8]}"
        
        channel = create_channel_instance(
            session,
            tenant_id=tenant.id,
            channel_type=ChannelType.whatsapp,
            identifier=channel_number,
            phone_number=channel_number.replace("whatsapp:", ""),
            extra={"display_name": "Test"}
        )
        
        # Use provided flow definition or create a simple default
        if flow_definition is None:
            flow_definition = {
                "schema_version": "v2",
                "id": "test_flow",
                "entry": "welcome",
                "nodes": [
                    {
                        "id": "welcome",
                        "kind": "Question",
                        "key": "intention",
                        "prompt": "What are you looking to accomplish today?"
                    },
                    {
                        "id": "complete", 
                        "kind": "Terminal",
                        "reason": "Thank you!"
                    }
                ],
                "edges": [
                    {
                        "source": "welcome", 
                        "target": "complete", 
                        "guard": {"fn": "answers_has", "args": {"key": "intention"}},
                        "priority": 0
                    }
                ]
            }
        
        flow = create_flow(
            session,
            tenant_id=tenant.id,
            channel_instance_id=channel.id,
            name=flow_name,
            flow_id=f"test_flow_{test_id}",
            definition=flow_definition
        )
        
        session.commit()
        return tenant, channel, flow, channel_number
        
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_sales_qualifier_flow() -> dict[str, Any]:
    """Create a sales qualifier flow definition for testing."""
    return {
        "schema_version": "v2",
        "id": "sales_qualifier",
        "entry": "start",
        "nodes": [
            {
                "id": "start",
                "kind": "Question",
                "key": "intention",
                "prompt": "O que você está buscando realizar hoje?"
            },
            {
                "id": "budget_question",
                "kind": "Question", 
                "key": "budget",
                "prompt": "Você tem alguma faixa de orçamento em mente?"
            },
            {
                "id": "timeframe_question",
                "kind": "Question",
                "key": "timeframe", 
                "prompt": "Qual é o seu prazo ideal?"
            },
            {
                "id": "complete",
                "kind": "Terminal",
                "reason": "Obrigado pelas informações!"
            }
        ],
        "edges": [
            {
                "source": "start",
                "target": "budget_question",
                "guard": {"fn": "answers_has", "args": {"key": "intention"}},
                "priority": 0
            },
            {
                "source": "budget_question", 
                "target": "timeframe_question",
                "guard": {"fn": "answers_has", "args": {"key": "budget"}},
                "priority": 0
            },
            {
                "source": "timeframe_question",
                "target": "complete",
                "guard": {"fn": "answers_has", "args": {"key": "timeframe"}},
                "priority": 0
            }
        ]
    }


def create_paths_flow(lock_threshold: int = 2) -> dict[str, Any]:
    """Create a flow with path selection for testing."""
    return {
        "schema_version": "v2",
        "id": "paths_flow",
        "entry": "start",
        "nodes": [
            {
                "id": "start",
                "kind": "Question",
                "key": "intention",
                "prompt": "What are you looking to accomplish today?"
            },
            {
                "id": "path_selection",
                "kind": "PathSelection",
                "paths": {
                    "tennis_court": {
                        "entry_predicates": [
                            {"type": "keyword", "any": ["tennis", "court"]}
                        ],
                        "questions": [
                            {
                                "key": "court_type",
                                "prompt": "Is it indoor or outdoor?",
                                "priority": 20
                            }
                        ]
                    },
                    "soccer_court": {
                        "entry_predicates": [
                            {"type": "keyword", "any": ["soccer", "football", "pitch"]}
                        ],
                        "questions": [
                            {
                                "key": "field_size", 
                                "prompt": "Approximate field size?",
                                "priority": 20
                            }
                        ]
                    }
                },
                "path_selection": {
                    "lock_threshold": lock_threshold,
                    "allow_switch_before_lock": True
                }
            },
            {
                "id": "budget_question",
                "kind": "Question",
                "key": "budget", 
                "prompt": "Do you have a budget range in mind?"
            },
            {
                "id": "timeframe_question",
                "kind": "Question",
                "key": "timeframe",
                "prompt": "What is your ideal timeline?"
            },
            {
                "id": "escalate",
                "kind": "Escalation",
                "reason": "Transferindo você para um atendente humano"
            },
            {
                "id": "complete",
                "kind": "Terminal", 
                "reason": "Thank you!"
            }
        ],
        "edges": [
            {
                "source": "start",
                "target": "path_selection",
                "guard": {"fn": "answers_has", "args": {"key": "intention"}},
                "priority": 0
            },
            {
                "source": "path_selection",
                "target": "budget_question", 
                "guard": {"fn": "always"},
                "priority": 0
            },
            {
                "source": "budget_question",
                "target": "timeframe_question",
                "guard": {"fn": "answers_has", "args": {"key": "budget"}},
                "priority": 0
            },
            {
                "source": "timeframe_question",
                "target": "escalate",
                "guard": {"fn": "answers_has", "args": {"key": "timeframe"}},
                "priority": 0
            }
        ]
    }
