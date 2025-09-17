"""Message generation service for creating natural, conversational responses.

This service is responsible for generating WhatsApp-style messages that feel natural
and human-like while preserving the intent of the communication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.tenant_config_service import ProjectContext

from ..constants import (
    BR_CONTRACTIONS,
    MAX_FOLLOWUP_DELAY_MS,
    MAX_MESSAGE_LENGTH,
    MAX_MESSAGES_PER_TURN,
    MIN_FOLLOWUP_DELAY_MS,
    MIN_MESSAGES_PER_TURN,
    NO_DELAY_MS,
)


class MessageGenerationService:
    """Service for generating natural, conversational messages."""

    def __init__(self) -> None:
        """Initialize the message generation service."""
        self._default_style = "warm_receptionist"

    def generate_messages(
        self,
        content: str,
        context: dict[str, Any] | None = None,
        project_context: ProjectContext | None = None,
        max_messages: int = MAX_MESSAGES_PER_TURN,
    ) -> list[dict[str, Any]]:
        """Generate WhatsApp-style messages from content.

        Args:
            content: The main content to convey
            context: Optional context about the conversation state
            project_context: Optional project-specific context and style
            max_messages: Maximum number of message bubbles to generate

        Returns:
            List of message objects with text and delay_ms
        """
        if not content:
            return []

        # For now, return a simple single message
        # The actual generation logic will be handled by GPT-5 in the responder
        return [{"text": content.strip(), "delay_ms": NO_DELAY_MS}]

    def build_generation_instructions(
        self,
        is_completion: bool = False,
        has_custom_style: bool = False,
    ) -> str:
        """Build instructions for message generation.

        Args:
            is_completion: Whether this is a flow completion message
            has_custom_style: Whether custom communication style is provided

        Returns:
            Instruction text for the LLM
        """
        instructions = []

        # Core messaging principles (natural PT-BR, avoid robotic phrasing)
        instructions.append(f"""
MESSAGING PRINCIPLES:
- Generate {MIN_MESSAGES_PER_TURN}-{MAX_MESSAGES_PER_TURN} natural WhatsApp messages
- First message has delay_ms={NO_DELAY_MS}
- Follow-ups have delay_ms between 1500-2200 (aprox.)
- Keep messages concise (max {MAX_MESSAGE_LENGTH} chars each)
- Sound natural in PT-BR (simples, direto, educado). Evite frases de call center
- Use Brazilian Portuguese natural expressions
- Avoid repetitive greetings or acknowledgments
- Emojis são opcionais e moderados (0-1, somente quando fizer sentido)
""")

        if is_completion:
            instructions.append("""
COMPLETION CONTEXT:
- This is the final message of the flow
- Thank the user and indicate you'll follow up
- Example: "Perfeito! Vou verificar isso e te retorno em breve."
""")

        if not has_custom_style:
            instructions.append(f"""
DEFAULT STYLE:
- Profissional, mas próximo e humano
- Português brasileiro natural
- Evite burocratês (ex.: "Para dar sequência", "Me conta:", "Anotei seu email")
- Use contrações naturalmente: {", ".join(repr(c) for c in BR_CONTRACTIONS[:2])}
- Termine perguntas de forma simples com '?'
""")

        return "\n".join(instructions)

    def format_messages_json(self, messages: list[dict[str, Any]]) -> str:
        """Format messages as JSON for the response.

        Args:
            messages: List of message objects

        Returns:
            JSON string representation
        """
        import json

        return json.dumps(messages, ensure_ascii=False, indent=2)
