from __future__ import annotations

import re
from typing import TYPE_CHECKING

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
    "4. Se o usuário fez PERGUNTA → Seja prestativa sem reconhecimentos desnecessários\n\n"
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


def naturalize_prompt(
    llm: LLMClient,  # type: ignore[name-defined]
    text: str,
    instruction: str | None = None,
    project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    conversation_context: list[dict[str, str]] | None = None,
) -> str:
    """
    Naturalize a prompt for WhatsApp with optional project context and conversation history.

    Args:
        llm: LLM client for rewriting
        text: Original text to rewrite
        instruction: Custom instruction (overrides default)
        project_context: Business context for better communication style
        conversation_context: Recent conversation history for context
    """
    # If project context has a communication style, use it to build custom instruction
    if project_context and project_context.communication_style:
        instr = _build_custom_style_instruction(
            project_context.communication_style, is_single_message=True
        )
    else:
        # Use default instruction for standard tone (no custom style)
        instr = instruction or DEFAULT_INSTRUCTION
        # Add minimal project context if available but no communication style
        if project_context and project_context.has_rewriter_context():
            context_prompt = project_context.get_rewriter_context_prompt()
            instr = f"{instr}\n{context_prompt}"

    # Build context-aware input for the LLM
    llm_input = f"Texto para naturalizar: {text}"

    if conversation_context:
        context_str = "\n".join(
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in conversation_context
        )
        llm_input += f"\n\nHISTÓRICO DA CONVERSA (apenas para TOM - JAMAIS copiar conteúdo daqui):\n{context_str}"

    try:
        rewritten = llm.rewrite(instr, llm_input)

        # Log the prompt and response
        prompt_logger.log_prompt(
            prompt_type="naturalize_single",
            instruction=instr,
            input_text=llm_input,
            response=rewritten if isinstance(rewritten, str) else str(rewritten),
            model=getattr(llm, "model_name", "unknown"),
            metadata={"has_project_context": project_context is not None},
        )

        if isinstance(rewritten, str) and rewritten.strip():
            # Defensive sanitization to ensure single-line question
            first_line = next(
                (ln.strip() for ln in rewritten.splitlines() if ln.strip()), ""
            )
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if (
                first_line.startswith('"')
                and first_line.endswith('"')
                and len(first_line) > 1
            ):
                first_line = first_line[1:-1].strip()
            return first_line or text
        return text
    except Exception as e:
        # Log the error too
        prompt_logger.log_prompt(
            prompt_type="naturalize_single_error",
            instruction=instr,
            input_text=llm_input,
            response=f"ERROR: {e}",
            model=getattr(llm, "model_name", "unknown"),
            metadata={"error": str(e)},
        )
        return text


def clarify_and_reask(
    llm: LLMClient,  # type: ignore[name-defined]
    question_text: str,
    user_message: str,
    project_context: ProjectContext | None = None,  # type: ignore[name-defined]
) -> str:
    """
    Produce a brief, casual PT-BR acknowledgement referencing the user's words,
    then restate the original question succinctly in one sentence.

    Args:
        llm: LLM client for rewriting
        question_text: The original question to clarify
        user_message: The user's clarification request
        project_context: Business context for appropriate communication style
    """
    # If project context has a communication style, use it for clarification
    if project_context and project_context.communication_style:
        instr = (
            "CONTEXTO: O usuário não entendeu sua pergunta e pediu esclarecimento. "
            "Você precisa reconhecer gentilmente e reformular a pergunta de forma mais clara.\n\n"
        )

        # Add the custom style instruction
        style_instruction = _build_custom_style_instruction(
            project_context.communication_style, is_single_message=True
        )
        instr += style_instruction
        instr += "\nRESPOSTA REQUERIDA: Uma frase que reconheça a dúvida do usuário e reformule a pergunta original de forma mais clara, seguindo exatamente o padrão de comunicação especificado.\n"
    else:
        # Default clarification style
        instr = (
            "CONTEXTO: Você é uma recepcionista brasileira profissional. A pessoa não entendeu sua pergunta e pediu esclarecimento.\n\n"
            "RESPOSTA CONCISA E PROFISSIONAL:\n"
            "Construa UMA frase cordial que:\n"
            "- Reconheça gentilmente ('ah, claro', 'certo', 'sem problemas')\n"
            "- Reformule de forma mais clara e simples\n"
            "- Máximo 1-2 linhas no WhatsApp\n"
            "- Tom: recepcionista simpática mas competente\n\n"
            "EXEMPLOS DE TOM ADEQUADO:\n"
            "- 'Claro! Preciso saber as dimensões do galpão - comprimento e largura em metros'\n"
            "- 'Sem problemas! Qual o tamanho do espaço? Tipo 15x20 metros?'\n"
            "- 'Certo, deixa eu reformular: quantos metros tem de comprimento e largura?'\n\n"
            "CRÍTICO:\n"
            "- NÃO faça listas numeradas ou explicações longas\n"
            "- NÃO seja muito casual ('E aí', 'foi mal', 'ops')\n"
            "- NÃO seja muito formal ('Senhor/Senhora', 'poderia informar')\n"
            "- SÓ reformule a pergunta de forma clara e cordial\n"
            "- Tom de recepcionista brasileira profissional\n"
        )

        # Add minimal project context if available but no communication style
        if project_context and project_context.has_rewriter_context():
            context_prompt = project_context.get_rewriter_context_prompt()
            instr = f"{instr}\n{context_prompt}"

    try:
        text = f"Pergunta: {question_text}\nUsuário perguntou: {user_message}"
        rewritten = llm.rewrite(instr, text)

        # Log the prompt and response
        prompt_logger.log_prompt(
            prompt_type="clarify_reask",
            instruction=instr,
            input_text=text,
            response=rewritten if isinstance(rewritten, str) else str(rewritten),
            model=getattr(llm, "model_name", "unknown"),
            metadata={"has_project_context": project_context is not None},
        )

        if isinstance(rewritten, str) and rewritten.strip():
            first_line = next(
                (ln.strip() for ln in rewritten.splitlines() if ln.strip()), ""
            )
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if (
                first_line.startswith('"')
                and first_line.endswith('"')
                and len(first_line) > 1
            ):
                first_line = first_line[1:-1].strip()
            return first_line
        return question_text
    except Exception as e:
        # Log the error
        prompt_logger.log_prompt(
            prompt_type="clarify_reask_error",
            instruction=instr,
            input_text=text,
            response=f"ERROR: {e}",
            model=getattr(llm, "model_name", "unknown"),
            metadata={"error": str(e)},
        )
        return question_text


def rewrite_whatsapp_multi(
    llm: LLMClient,  # type: ignore[name-defined]
    original_text: str,
    chat_window: list[dict[str, str]] | None = None,
    *,
    max_followups: int = 2,
    project_context: ProjectContext | None = None,  # type: ignore[name-defined]
) -> list[dict[str, int | str]]:
    """Rewrite an assistant reply into human-like WhatsApp-style messages.

    Returns a list of {"text": str, "delay_ms": int} objects. The first message should have
    delay_ms=0. Follow-ups should be paced to feel human.

    If rewriting fails, returns a single message with original_text.
    """
    if not original_text.strip():
        return [{"text": original_text, "delay_ms": 0}]

    # Proceed to rewrite even for direct questions. Post-processing below preserves
    # the exact question wording and ensures a single question bubble.

    history_lines: list[str] = []
    for turn in chat_window or []:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()
        if role and content:
            history_lines.append(f"{role}: {content}")

    history_block = "\n".join(history_lines[-200:])  # cap to keep prompt bounded

    # Use custom style instruction if communication style is provided
    if project_context and project_context.communication_style:
        instruction = _build_custom_style_instruction(
            project_context.communication_style, is_single_message=False
        )
    else:
        # Default instruction when no custom communication style is provided
        instruction = (
            "Você está naturalizando mensagens para soar mais brasileira e calorosa no WhatsApp.\n\n"
            "REGRA FUNDAMENTAL - PRESERVE O ASSUNTO ORIGINAL:\n"
            "- JAMAIS adicione assuntos que não estão na mensagem original\n"
            "- Se a mensagem original fala sobre PLANO DE SAÚDE → fale APENAS sobre plano de saúde\n"
            "- Se a mensagem original fala sobre DISPONIBILIDADE → fale APENAS sobre disponibilidade\n"
            "- Use o histórico apenas para entender contexto, JAMAIS para copiar conteúdo\n\n"
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
            "- No MESMO TURNO, use no máximo UMA saudação (de preferência na primeira mensagem)\n"
            "- Se já houve saudação neste turno, NÃO repita nas mensagens seguintes\n"
            "- Se não for primeira interação e o usuário não saudou, vá direto ao ponto (sem saudação)\n"
            "- A mensagem final de pergunta NÃO deve conter saudação se já houve saudação no turno\n\n"
            "ADAPTAÇÃO INTELIGENTE:\n"
            "Observe padrões do usuário e adapte adequadamente:\n"
            "- Usuário formal → mantenha mais profissional\n"
            "- Usuário casual → seja calorosa mas ainda cordial\n"
            "- Usuário é breve → seja concisa\n"
            "- Usuário elabora → você pode desenvolver mais\n\n"
            "DECISÕES IMPORTANTES:\n"
            "- Quando houver OPÇÕES: apresente cordialmente ('seria consulta, exame, ou outro serviço?' ao invés de menu numerado)\n"
            "- Para ESCLARECIMENTOS: reconheça gentilmente antes de esclarecer\n"
            "- Em CONFIRMAÇÕES: seja cordial ('Perfeito! Anotei aqui' ao invés de só 'Ok')\n"
            "- Para INFORMAÇÕES: seja positiva ('Consegui um ótimo horário!' ao invés de só 'Horário disponível:')\n\n"
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
        if (
            project_context
            and project_context.has_rewriter_context()
            and not project_context.communication_style
        ):
            context_prompt = project_context.get_rewriter_context_prompt()
            instruction = f"{instruction}\n{context_prompt}"

    history_block = "\n".join(history_lines[-200:])  # cap to keep prompt bounded

    payload = (
        f"Original assistant reply:\n{original_text}\n\n"
        f"Conversation history (for tone context only):\n{history_block}"
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
            if clean_raw.startswith('```json') and clean_raw.endswith('```'):
                clean_raw = clean_raw[7:-3].strip()
            elif clean_raw.startswith('```') and clean_raw.endswith('```'):
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
            return out
    except Exception:
        # Fall through to deterministic fallback below
        pass

    # Simple fallback: if LLM fails, return original text as-is
    return [{"text": original_text, "delay_ms": 0}]


def _build_custom_style_instruction(
    communication_style: str, is_single_message: bool = False
) -> str:
    """
    Build a custom instruction that mimics the provided communication style.

    Args:
        communication_style: The tenant's communication style (could be instructions or examples)
        is_single_message: If True, builds instruction for single message rewrite
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
    base_instruction = (
        "Você deve seguir o ESTILO DE COMUNICAÇÃO do cliente descrito abaixo, aplicando-o naturalmente.\n\n"
        "ESTILO DE COMUNICAÇÃO DO CLIENTE:\n"
        f"{communication_style}\n\n"
        "COMO APLICAR O ESTILO:\n"
        "• Absorva o TOM, PERSONALIDADE e LINGUAGEM do estilo acima\n"
        "• Aplique esse estilo naturalmente à sua mensagem\n"
        "• MANTENHA sempre o assunto da mensagem original\n"
        "• Varie as expressões - não copie frases específicas literalmente\n"
        "REGRAS DE SAUDAÇÃO:\n"
        "• Evite saudar novamente a cada turno; cumprimente só quando fizer sentido (ex.: início)\n"
        "• Se já houve saudação recente, vá direto ao ponto sem repetir 'oi', 'e aí', etc.\n"
        "• Em múltiplas mensagens do mesmo turno, use saudação no máximo uma vez (de preferência na primeira)\n"
        "REGRA FUNDAMENTAL:\n"
        "• O ASSUNTO da mensagem original é sagrado - nunca misture outros tópicos\n"
        "• Se a mensagem é sobre plano de saúde → fale apenas sobre plano de saúde\n"
        "• Se é sobre disponibilidade → fale apenas sobre disponibilidade\n"
        "• Aplique o estilo do cliente MAS preserve o conteúdo original\n\n"
    )

    if is_single_message:
        # Single message instruction
        return (
            f"{base_instruction}"
            "FORMATO DE SAÍDA:\n"
            "• Reescreva em UMA frase natural seguindo o estilo do cliente\n"
            "• Mantenha 100% do significado original\n"
            "• Aplique apenas o tom, não altere o conteúdo\n"
        )
    else:
        # Multi-message instruction
        return (
            f"{base_instruction}"
            "ESTRATÉGIA DE MÚLTIPLAS MENSAGENS:\n"
            "• Siga o estilo natural do cliente\n"
            "• Divida o conteúdo de forma conversacional\n"
            "• Última mensagem sempre deve ser a pergunta principal\n\n"
            'Formato: JSON array [{"text": string, "delay_ms": number}]\n'
            "Delays: primeira sempre 0, outras entre 2000-4000ms\n"
        )
