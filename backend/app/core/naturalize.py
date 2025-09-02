from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .langfuse_client import get_langfuse_client, trace_llm_call
from .prompt_logger import prompt_logger

if TYPE_CHECKING:  # avoid hard import at runtime
    from app.services.tenant_config_service import ProjectContext

    from .llm import LLMClient

# Human pacing defaults for multi-message outputs
MIN_FOLLOWUP_DELAY_MS = 2200
MAX_FOLLOWUP_DELAY_MS = 4000
MAX_MULTI_MESSAGES = 8

DEFAULT_INSTRUCTION = (
    "CONTEXTO: Você está naturalizando mensagens para soar mais brasileira e natural no WhatsApp.\n\n"
    "TOM PADRÃO (quando não há estilo customizado):\n"
    "- Profissional mas calorosa\n"
    "- Natural e brasileira\n"
    "- Simpática mas respeitosa\n\n"
    "ANÁLISE CONTEXTUAL CRÍTICA:\n"
    "1. Se NÃO há mensagem do usuário ou é primeira interação → Seja acolhedora: 'Olá! Como posso ajudar?'\n"
    "2. Se o usuário deu uma RESPOSTA/INFORMAÇÃO → Reconheça adequadamente: 'Perfeito!', 'Ótimo!', 'Entendi!'\n"
    "3. Se o usuário fez SAUDAÇÃO ('oi', 'olá') → Responda à saudação: 'Oi! Tudo bem?', 'Olá!'\n"
    "4. Se o usuário fez PERGUNTA → Seja prestativa sem reconhecimentos desnecessários\n"
    "5. Se JÁ HOUVE SAUDAÇÃO na conversa → NUNCA repita saudações, vá direto ao ponto\n\n"
    "TRANSFORMAÇÃO RESTRITIVA:\n"
    "Reescreva em UMA frase que:\n"
    "- Mantenha EXATAMENTE o mesmo ASSUNTO PRINCIPAL da pergunta original\n"
    "- Mantenha EXATAMENTE as mesmas PALAVRAS-CHAVE da pergunta original\n"
    "- Apenas ajuste o TOM para soar mais natural (brasileiro, caloroso)\n"
    "- NÃO adicione tópicos, assuntos ou elementos que não estão na pergunta original\n"
    "- NÃO invente conteúdo novo - apenas naturalize o que já existe\n"
    "VARIEDADE NATURAL:\n"
    "- EVITE reconhecimentos genéricos quando não fazem sentido\n"
    "- Varie inícios CONFORME O CONTEXTO: reconhecimento, saudação, ou pergunta direta\n"
    "- Mantenha naturalidade sem ser repetitivo\n"
    "- NÃO repita saudações a cada turno; cumprimente só na primeira interação ou quando fizer sentido\n"
    "- Evite iniciar mensagens consecutivas com saudação; varie ou vá direto ao ponto\n\n"
    "USO INTELIGENTE DO HISTÓRICO:\n"
    "- O HISTÓRICO DA CONVERSA é fornecido APENAS para entender o TOM e ESTILO adequado\n"
    "- Use o histórico para manter CONSISTÊNCIA de linguagem (formal vs casual)\n"
    "- JAMAIS copie palavras, frases ou elementos específicos do histórico\n"
    "- JAMAIS misture ASSUNTOS de perguntas anteriores na pergunta atual\n"
    "- Cada pergunta deve ser naturalizada baseada EXCLUSIVAMENTE em seu próprio significado\n\n"
    "FOQUE EXCLUSIVAMENTE NO ASSUNTO:\n"
    "- Mantenha sempre o assunto principal da pergunta original\n"
    "- Não adicione elementos de outros tópicos ou conversas anteriores\n"
    "- Naturalize apenas o estilo, preservando o conteúdo\n\n"
    "NATURALIDADE PROFISSIONAL:\n"
    "- Use contrações naturais: 'tá', 'pra', 'né', mas com moderação\n"
    "- Finalize cordialmente: '?' simples, 'certo?', ou sem nada\n"
    "- Evite tanto formalidade excessiva quanto casualidade demais\n"
    "- Tom: como uma recepcionista que você adora conversar mas que é competente\n\n"
    "REGRA OBRIGATÓRIA - PERGUNTAS DEVEM CONTINUAR SENDO PERGUNTAS:\n"
    "- Se o texto original TERMINA com '?' → sua naturalização DEVE terminar com uma pergunta\n"
    "- Se o texto original é claramente uma PERGUNTA → SEMPRE termine com '?' para manter o fluxo\n"
    "- A pergunta naturalizada deve ser sobre o MESMO ASSUNTO da pergunta original\n"
    "- Exemplo: 'Você pode vir agora?' → 'Consegue vir agora?' (mesmo assunto, naturalizado)\n"
    "- JAMAIS transforme pergunta em afirmação - sempre mantenha conversa fluindo pra completar os objetivos.\n\n"
    "REGRA ABSOLUTA - ASSUNTO É SAGRADO:\n"
    "- O ASSUNTO da pergunta original NUNCA pode ser alterado\n"
    "- Você pode mudar apenas o ESTILO, JAMAIS o CONTEÚDO ou ASSUNTO\n\n"
    "- EVITE MAIS DE UMA OU DUAS PERGUNTAS EM UMA MENSAGEM OU TURNO. Mesmo que a pergunta seja curta. Muitas interrogações podem ser chamativas e desagradáveis.\n\n"
    "- NAO USE MAIS DE UMA SAUDACAO, POR EXEMPLO E AÍ, POR CONVERSA.\n\n"
)

def rewrite_whatsapp_multi(
    llm: LLMClient,  # type: ignore[name-defined]
    original_text: str,
    chat_window: list[dict[str, str]] | None = None,
    *,
    max_followups: int = 2,
    project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    is_completion: bool = False,
) -> list[dict[str, int | str]]:
    """Rewrite an assistant reply into human-like WhatsApp-style messages.

    Returns a list of {"text": str, "delay_ms": int} objects. The first message should have
    delay_ms=0. Follow-ups should be paced to feel human.

    Args:
        is_completion: Whether this is the final message/completion of the conversation flow

    If rewriting fails, returns a single message with original_text.
    """
    if not original_text.strip():
        return [{"text": original_text, "delay_ms": 0}]

    # Proceed to rewrite even for direct questions. Post-processing below preserves
    # the exact question wording and ensures a single question bubble.

    history_lines: list[str] = []
    for i, turn in enumerate(chat_window or []):
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()
        if role and content:
            # Add sequence number and role for clarity
            sequence = i + 1
            history_lines.append(f"[{sequence}] {role}: {content}")

    # Take last 10 turns and ensure chronological order (oldest first)
    recent_history = history_lines[-10:] if history_lines else []
    history_block = "\n".join(recent_history) if recent_history else "No previous conversation"

    # Use custom style instruction if communication style is provided
    if project_context and project_context.communication_style:
        instruction = _build_custom_style_instruction(
            project_context.communication_style, is_single_message=False, is_completion=is_completion
        )
    else:
        # Default instruction when no custom communication style is provided
        completion_context = ""
        if is_completion:
            completion_context = (
                "CONTEXTO CRÍTICO - FINALIZAÇÃO DA CONVERSA:\n"
                "Esta é a ÚLTIMA interação da conversa. O fluxo foi completado.\n"
                "- RESPONDA com uma mensagem genérica de agradecimento e que retornará em breve\n"
                "- Use algo como: 'Ok. Obrigado! Vou entrar em contato com você em breve.'\n"
                "- OU similar: 'Perfeito! Vou verificar isso e te retorno.'\n"
                "- NÃO mencione especificamente 'humano' mas indique que retornará\n"
                "- Seja cordial mas deixe claro que a conversa está pausada temporariamente\n"
                "- Mantenha tom profissional e reassegurador\n\n"
            )

        instruction = (
            f"{completion_context}"
            "Você está naturalizando mensagens para soar mais brasileira e calorosa no WhatsApp.\n\n"
            "REGRA FUNDAMENTAL - PRESERVE O ASSUNTO ORIGINAL:\n"
            "- JAMAIS adicione assuntos que não estão na mensagem original\n"
            "- Se a mensagem original fala sobre PLANO DE SAÚDE → fale APENAS sobre plano de saúde\n"
            "- Se a mensagem original fala sobre DISPONIBILIDADE → fale APENAS sobre disponibilidade\n"
            "- Use o histórico apenas para entender contexto, JAMAIS para copiar conteúdo\n"
            "- IGNORE completamente o Business Context - ele NÃO é parte da conversa\n"
            "- Business Context é apenas para você entender que empresa representa\n\n"
            "ANÁLISE CONTEXTUAL (FAÇA ISSO PRIMEIRO):\n"
            "Antes de responder, analise profundamente:\n"
            "1. O tom emocional da última mensagem do usuário (animado? confuso? neutro? frustrado? curioso?)\n"
            "2. O contexto da conversa até agora (primeira interação? já conversaram? qual o assunto?)\n"
            "3. O tipo de resposta necessária (informação? confirmação? escolha? esclarecimento?)\n"
            "4. A complexidade da resposta (simples = 1 msg, média = 2 msgs, complexa = 3+ msgs)\n\n"
            "ADAPTAÇÃO CONTEXTUAL:\n"
            "- Adapte o tom baseado no contexto da conversa\n"
            "- Mantenha consistência com o padrão estabelecido\n"
            "- Seja natural sem exageros\n\n"
            "ESTRATÉGIA DE MENSAGENS:\n"
            "Decida quantas mensagens baseado no CONTEÚDO e CONTEXTO:\n\n"
            "• 1 MENSAGEM quando:\n"
            "  - Pergunta simples e direta (nome, horário, sim/não)\n"
            "  - Confirmação rápida\n"
            "  - Usuário parece apressado\n"
            "  Exemplo: pergunta 'Qual seu nome?' → resposta 'Me chamo Ana! E você?'\n\n"
            "• 2 MENSAGENS quando:\n"
            "  - Precisa reconhecer + perguntar\n"
            "  - Informação + confirmação\n"
            "  - Criar conexão emocional + conteúdo\n"
            "  Exemplo: usuário confuso → 'Ah, entendi sua dúvida!' + 'É assim: [explicação]'\n\n"
            "• 3+ MENSAGENS quando:\n"
            "  - Explicação em etapas\n"
            "  - Múltiplas opções para escolher\n"
            "  - História ou contextualização\n"
            "  - Usuário muito engajado (merece atenção extra)\n"
            "  Exemplo: processo complexo → 'Ok, vou te explicar!' + 'Primeiro, você...' + 'Depois é só...'\n\n"
            "ORDEM OBRIGATÓRIA DAS MENSAGENS:\n"
            "- PRIMEIRA(S) mensagem(ns): Reconhecimentos, confirmações, saudações, comentários\n"
            "- ÚLTIMA mensagem: SEMPRE a pergunta principal que drive a conversa\n"
            "- A pergunta que solicita informação do usuário DEVE ser a última mensagem\n"
            "- Cada mensagem deve focar no ASSUNTO PRINCIPAL da mensagem original\n"
            "- Mantenha coerência: todas as mensagens devem abordar o mesmo assunto\n\n"
            "PRESERVE O ASSUNTO ORIGINAL:\n"
            "- Mantenha o foco no assunto da mensagem original\n"
            "- Use o histórico apenas para entender o estilo de linguagem\n"
            "- Não adicione elementos de outras conversas ou tópicos\n\n"
            "TÉCNICAS DE NATURALIDADE PROFISSIONAL:\n"
            "- Varie inícios cordiais naturalmente\n"
            "- Use elementos do português brasileiro com moderação\n"
            "- Mantenha tom profissional mas caloroso\n"
            "- Adapte-se ao estilo sem repetir sempre as mesmas expressões\n\n"
            "REGRAS DE SAUDAÇÃO (CRÍTICO):\n"
            "- Se o texto original contém saudação (Olá, Oi), preserve-a naturalmente\n"
            "- Se já há saudação no histórico, evite repetir, mas preserve o tom da mensagem original\n\n"
            "MANTER CONTEXTO DE NEGÓCIO (CRÍTICO):"
            "- SEMPRE mantenha o foco no propósito do negócio (ex: iluminação, saúde, etc.)\n"
            "- Se o usuário faz perguntas fora do escopo (admin, sistema, meta), responda brevemente mas SEMPRE redirecione para o negócio\n"
            "- Exemplo: pergunta sobre admin → 'Sou assistente de vendas. Em que posso ajudá-lo com nossos produtos?'\n"
            "- NUNCA entre em discussões técnicas sobre sistemas, permissões ou funcionalidades internas.\n"
            "- A ÚLTIMA mensagem deve SEMPRE puxar de volta para o foco principal do negócio\n"
            "ADAPTAÇÃO INTELIGENTE:\n"
            "Observe padrões do usuário e adapte adequadamente:\n"
            "- Usuário formal → mantenha mais profissional\n"
            "- Usuário casual → seja calorosa mas ainda cordial\n"
            "- Usuário é breve → seja concisa\n"
            "- Usuário elabora → você pode desenvolver mais\n\n"
            "DECISÕES IMPORTANTES:\n"
            "- Quando houver OPÇÕES: apresente cordialmente ('seria consulta, exame, ou outro serviço?' ao invés de menu numerado)\n"
            "- Para ESCLARECIMENTOS: reconheça gentilmente antes de esclarecer\n"
            "- Em CONFIRMAÇÕES: seja cordial ('Perfeito! Anotei aqui' ao invés de só 'Ok')\n\n"
            "AUTENTICIDADE PROFISSIONAL:\n"
            "- Seja humana mas mantendo competência\n"
            "- Demonstre interesse genuíno pelo cliente\n"
            "- Use diminutivos carinhosos quando apropriado: 'minutinho', 'rapidinho'\n"
            "- Mantenha sempre o equilíbrio: calorosa mas respeitosa\n\n"
            'Formato: JSON array [{"text": string, "delay_ms": number}]\n'
            "Delays: primeira sempre 0, outras entre 2200-3800ms (varie para parecer natural)\n"
            "Tamanho: máximo 150 caracteres por mensagem, mas varie (algumas bem curtas como 'Perfeito!' outras maiores)\n"
        )

        # Add minimal project context if available but no communication style
        # Only inject business context for substantive content, not simple greetings
        if (
            project_context
            and project_context.has_rewriter_context()
            and not project_context.communication_style
            and len(original_text.strip()) > 50  # Avoid injecting for short/simple messages
        ):
            context_prompt = project_context.get_rewriter_context_prompt()
            instruction = f"{instruction}\n{context_prompt}"

    history_block = "\n".join(history_lines[-200:])  # cap to keep prompt bounded

    payload = f"""=== ORIGINAL MESSAGE TO REWRITE ===
{original_text}

=== CONVERSATION HISTORY (for tone reference only) ===
{history_block}

=== BUSINESS CONTEXT (for company understanding only) ===
Business: {project_context.project_description if project_context else 'Customer service'}

=== INSTRUÇÕES CRÍTICAS ===
1. Reescreva APENAS a seção "Original message to rewrite" acima
2. O contexto de negócio é só para você saber que empresa representa
3. NÃO adicione detalhes de negócio que não estão na mensagem original
4. NÃO trate o contexto de negócio como parte da conversa
5. Preserve o conteúdo central e significado da mensagem original
6. Apenas ajuste o tom e estilo para ser mais conversacional

=== SUA TAREFA ===
Pegue a mensagem original e torne-a mais natural e conversacional preservando exatamente seu significado e conteúdo.
"""

    # Create Langfuse trace for naturalization
    langfuse_client = get_langfuse_client()
    trace = None
    if langfuse_client.is_enabled():
        # Extract user context from chat window if available
        user_id = None
        session_id = None
        if chat_window:
            # Try to extract user/session from chat context
            for turn in chat_window[-3:]:  # Check last 3 turns for context
                if turn.get("role") == "user" and "user_id" in str(turn):
                    # This would need actual user context extraction logic
                    pass

        trace = langfuse_client.create_trace(
            name="whatsapp_naturalization",
            user_id=user_id,
            session_id=session_id,
            metadata={
                "operation": "text_naturalization",
                "style": "whatsapp_multi",
                "has_project_context": project_context is not None,
                "has_custom_style": project_context.communication_style if project_context else False,
                "is_completion": is_completion,
                "max_followups": max_followups,
                "history_messages": len(history_lines),
                "original_text_length": len(original_text),
                "instruction_length": len(instruction),
                "payload_length": len(payload),
            },
            tags=[
                "naturalization", 
                "whatsapp", 
                "multi_message",
                "completion" if is_completion else "conversation",
                getattr(llm, "model_name", "unknown"),
            ],
        )

    try:
        raw = llm.rewrite(instruction, payload)

        # Log the prompt and response
        prompt_logger.log_prompt(
            prompt_type="whatsapp_multi",
            instruction=instruction,
            input_text=payload,
            response=raw if isinstance(raw, str) else str(raw),
            model=getattr(llm, "model_name", "unknown"),
            metadata={
                "has_project_context": project_context is not None,
                "max_followups": max_followups,
                "history_messages": len(history_lines),
            },
        )

        # Parse JSON array (handle both plain and markdown-wrapped JSON for consistency)
        import json

        # Strip markdown code blocks if present - ensures consistent parsing regardless of LLM behavior
        clean_raw = raw
        if isinstance(raw, str):
            clean_raw = raw.strip()
            # Remove markdown JSON code blocks
            if clean_raw.startswith("```json") and clean_raw.endswith("```"):
                clean_raw = clean_raw[7:-3].strip()
            elif clean_raw.startswith("```") and clean_raw.endswith("```"):
                clean_raw = clean_raw[3:-3].strip()

        messages = json.loads(clean_raw) if isinstance(clean_raw, str) else []
        out: list[dict[str, int | str]] = []
        if isinstance(messages, list):
            for i, item in enumerate(messages):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                try:
                    delay_ms_val = int(item.get("delay_ms", 0))
                except Exception:
                    delay_ms_val = 0 if i == 0 else MIN_FOLLOWUP_DELAY_MS
                if i == 0:
                    delay_ms_val = 0
                out.append({"text": text, "delay_ms": max(0, delay_ms_val)})
                # Soft cap to prevent pathological outputs; keep generous to feel free-form
                if len(out) >= MAX_MULTI_MESSAGES:
                    break
        if out:
            # Normalize follow-up delays into human pacing range
            for idx in range(1, len(out)):
                try:
                    d = int(out[idx].get("delay_ms", MIN_FOLLOWUP_DELAY_MS))
                except Exception:
                    d = MIN_FOLLOWUP_DELAY_MS
                if d < MIN_FOLLOWUP_DELAY_MS:
                    d = MIN_FOLLOWUP_DELAY_MS
                elif d > MAX_FOLLOWUP_DELAY_MS:
                    d = MAX_FOLLOWUP_DELAY_MS
                out[idx]["delay_ms"] = d
            # Trace successful naturalization
            if trace:
                trace.generation(
                    name="naturalization_llm_call",
                    model=getattr(llm, "model_name", "unknown"),
                    input=payload,
                    output=raw if isinstance(raw, str) else str(raw),
                    metadata={
                        "messages_generated": len(out),
                        "total_characters": sum(len(str(msg.get("text", ""))) for msg in out),
                        "avg_delay_ms": sum(int(msg.get("delay_ms", 0)) for msg in out[1:]) / max(len(out) - 1, 1),
                        "has_markdown_cleanup": clean_raw != raw,
                        "json_parsed_successfully": True,
                        "style_applied": "custom" if project_context and project_context.communication_style else "default",
                    },
                    tags=["successful_naturalization", "multi_message"],
                )

                # Trace individual messages
                for i, msg in enumerate(out):
                    trace.event(
                        name=f"message_{i+1}",
                        input={"position": i+1, "is_first": i == 0},
                        output={"text": msg.get("text"), "delay_ms": msg.get("delay_ms")},
                        metadata={
                            "message_length": len(str(msg.get("text", ""))),
                            "delay_category": "immediate" if msg.get("delay_ms", 0) == 0 else "delayed",
                        },
                    )

            return out
    except Exception as e:
        # Trace the error
        if trace:
            trace.event(
                name="naturalization_error",
                input={"original_text": original_text, "instruction_length": len(instruction)},
                output={"error": str(e), "fallback_used": True},
                metadata={
                    "error_type": type(e).__name__,
                    "parsing_stage": "json_parsing" if "json" in str(e).lower() else "llm_call",
                },
            )
        # Fall through to deterministic fallback below
        pass

    # Simple fallback: if LLM fails, return original text as-is
    fallback_result = [{"text": original_text, "delay_ms": 0}]
    
    # Trace fallback usage
    if trace:
        trace.event(
            name="naturalization_fallback",
            input={"original_text": original_text},
            output={"fallback_result": fallback_result},
            metadata={
                "fallback_reason": "llm_failure_or_parsing_error",
                "preserved_original": True,
            },
        )
    
    return fallback_result


def _build_custom_style_instruction(
    communication_style: str, is_single_message: bool = False, is_completion: bool = False
) -> str:
    """
    Build a custom instruction that mimics the provided communication style.

    Args:
        communication_style: The tenant's communication style (could be instructions or examples)
        is_single_message: If True, builds instruction for single message rewrite
        is_completion: If True, builds instruction for conversation completion/closure
    """
    # Determine if the communication_style looks like conversation examples or instructions
    # Check for actual conversation formats (WhatsApp exports, chat logs, etc.)

    has_conversation_markers = any(
        [
            # WhatsApp export format: [date, time] Name: message
            re.search(r"\[\d+/\d+/\d+,\s+\d+:\d+:\d+\s+[AP]M\]", communication_style),
            # Generic timestamp format: [timestamp] Name: message
            re.search(r"\[\d{1,2}:\d{2}\].*?:", communication_style),
            # Chat platform indicators
            any(
                platform in communication_style.lower()
                for platform in ["whatsapp", "telegram", "discord", "slack", "teams"]
            ),
            # Conversation example markers (more specific)
            any(
                marker in communication_style.lower()
                for marker in [
                    "exemplo de conversa",
                    "exemplo:",
                    "conversa:",
                    "diálogo:",
                    "cliente:",
                    "recepcionista:",
                    "atendente:",
                    "usuário:",
                ]
            )
            and "\n" in communication_style,  # Must be multi-line to be a conversation
        ]
    )

    # Build instruction focused on following the custom style naturally
    completion_context = ""
    if is_completion:
        completion_context = (
            "CONTEXTO CRÍTICO - FINALIZAÇÃO DA CONVERSA:\n"
            "Esta é a ÚLTIMA interação da conversa. O fluxo foi completado.\n"
            "- RESPONDA no estilo do cliente com mensagem genérica que retornará em breve\n"
            "- Use algo como: 'Ok. Obrigado! Vou entrar em contato com você em breve.' (adaptado ao estilo)\n"
            "- OU similar: 'Perfeito! Vou verificar isso e te retorno.' (no estilo do cliente)\n"
            "- NÃO mencione especificamente 'humano' mas indique que retornará\n"
            "- Aplique o estilo do cliente para expressar essa pausa temporária cordialmente\n"
            "- Mantenha tom do cliente mas seja reassegurador\n\n"
        )

    base_instruction = (
        f"{completion_context}"
        "Você deve seguir o ESTILO DE COMUNICAÇÃO do cliente descrito abaixo, aplicando-o naturalmente.\n\n"
        "ESTILO DE COMUNICAÇÃO DO CLIENTE:\n"
        f"{communication_style}\n\n"
        "COMO APLICAR O ESTILO:\n"
        "• Absorva o TOM, PERSONALIDADE e LINGUAGEM do estilo acima\n"
        "• Aplique esse estilo naturalmente à sua mensagem\n"
        "• MANTENHA sempre o assunto da mensagem original\n"
        "• Varie as expressões - não copie frases específicas literalmente\n"
        "REGRAS DE SAUDAÇÃO:\n"
        "• CRÍTICO: Analise o histórico da conversa - se há saudações anteriores, NUNCA adicione novas\n"
        "• Evite saudar novamente a cada turno; cumprimente só quando fizer sentido (ex.: início)\n"
        "• Se já houve saudação recente, vá direto ao ponto sem repetir 'oi', 'e aí', 'olá', etc.\n"
        "• Em múltiplas mensagens do mesmo turno, use saudação no máximo uma vez (de preferência na primeira)\n"
        "• JAMAIS repita frases como 'Olá! Que bom ter você por aqui!' se já foram usadas\n"
        "REGRA FUNDAMENTAL:\n"
        "• O ASSUNTO da mensagem original é sagrado - nunca misture outros tópicos\n"
        "• Se a mensagem é sobre plano de saúde → fale apenas sobre plano de saúde\n"
        "• Se é sobre disponibilidade → fale apenas sobre disponibilidade\n"
        + ("• FINALIZAÇÃO: Responda com handoff temporário no estilo do cliente\n"
           "• Use algo como 'Vou te retornar em breve' adaptado ao estilo\n" if is_completion else
           "• PRESERVE PERGUNTAS: Se a mensagem original termina com '?', MANTENHA como pergunta\n"
           "• NUNCA transforme perguntas em afirmações ou suposições\n") +
        "• Aplique o estilo do cliente MAS preserve o conteúdo original\n\n"
    )

    if is_single_message:
        # Single message instruction
        return (
            f"{base_instruction}"
            "FORMATO DE SAÍDA:\n"
            "• Reescreva em UMA frase natural seguindo o estilo do cliente\n"
            "• Mantenha 100% do significado original\n"
            "• CRITICAL: Se a mensagem original termina com '?', sua resposta DEVE terminar com '?'\n"
            "• Aplique apenas o tom, não altere o conteúdo\n"
        )
    # Multi-message instruction
    strategy_text = (
        "• FINALIZAÇÃO: Divida a mensagem de handoff temporário no estilo do cliente\n"
        "• Primeira mensagem: Agradecimento/reconhecimento no estilo\n"
        "• Última mensagem: 'Vou entrar em contato em breve' no estilo do cliente\n"
        "• NÃO faça perguntas - expresse pausa cordial e retorno futuro\n\n" if is_completion else
        "• Siga o estilo natural do cliente\n"
        "• Divida o conteúdo de forma conversacional\n"
        "• Última mensagem sempre deve ser a pergunta principal\n"
        "• CRITICAL: Se a mensagem original termina com '?', a ÚLTIMA mensagem deve terminar com '?'\n"
        "• NUNCA transforme perguntas em confirmações ou afirmações\n\n"
    )

    return (
        f"{base_instruction}"
        f"ESTRATÉGIA DE MÚLTIPLAS MENSAGENS:\n"
        f"{strategy_text}"
        'Formato: JSON array [{"text": string, "delay_ms": number}]\n'
        "Delays: primeira sempre 0, outras entre 2000-4000ms\n"
    )
