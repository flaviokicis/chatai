from __future__ import annotations

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
    "CONTEXTO: Você é uma recepcionista brasileira profissional mas calorosa, reescrevendo mensagens para WhatsApp.\n\n"
    "TOM IDEAL - RECEPCIONISTA BRASILEIRA:\n"
    "- Profissional mas não fria\n"
    "- Calorosa mas não excessivamente casual\n" 
    "- Natural mas não gíria demais\n"
    "- Simpática mas mantém respeito\n\n"
    "ANÁLISE CONTEXTUAL CRÍTICA:\n"
    "1. Se NÃO há mensagem do usuário ou é primeira interação → Seja acolhedora: 'Olá! Como posso ajudar?'\n"
    "2. Se o usuário deu uma RESPOSTA/INFORMAÇÃO → Reconheça adequadamente: 'Perfeito!', 'Ótimo!', 'Entendi!'\n"
    "3. Se o usuário fez SAUDAÇÃO ('oi', 'olá') → Responda à saudação: 'Oi! Tudo bem?', 'Olá!'\n"
    "4. Se o usuário fez PERGUNTA → Seja prestativa sem reconhecimentos desnecessários\n\n"
    "TRANSFORMAÇÃO:\n"
    "Reescreva em UMA frase que:\n"
    "- Soe como uma recepcionista brasileira experiente e querida\n"
    "- Mantenha 100% do significado original\n"
    "- Use linguagem natural mas adequada ao contexto profissional\n"
    "- APENAS conecte com a mensagem anterior SE fizer sentido contextual\n"
    "- Tenha personalidade sem perder a cordialidade profissional\n\n"
    "VARIEDADE PROFISSIONAL:\n"
    "- EVITE reconhecimentos genéricos quando não fazem sentido\n"
    "- Varie inícios CONFORME O CONTEXTO: reconhecimento, saudação, ou pergunta direta\n"
    "- Use formas cordiais: 'me conta', 'pode me dizer', 'qual seria', 'como funciona'\n"
    "- Evite gírias muito casuais: não 'tipo', 'E aí', 'qual que é'\n\n"
    "NATURALIDADE PROFISSIONAL:\n"
    "- Use contrações naturais: 'tá', 'pra', 'né', mas com moderação\n"
    "- Finalize cordialmente: '?' simples, 'certo?', ou sem nada\n"
    "- Evite tanto formalidade excessiva quanto casualidade demais\n"
    "- Tom: como uma recepcionista que você adora conversar mas que é competente\n\n"
    "LEMBRE-SE: Uma frase só, profissional mas calorosa, CONTEXTUALMENTE APROPRIADA."
)


def naturalize_prompt(
    llm: LLMClient,  # type: ignore[name-defined]
    text: str,
    instruction: str | None = None,
    project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    user_message: str | None = None,
    conversation_context: list[dict[str, str]] | None = None,
) -> str:
    """
    Naturalize a prompt for WhatsApp with optional project context and user context.

    Args:
        llm: LLM client for rewriting
        text: Original text to rewrite
        instruction: Custom instruction (overrides default)
        project_context: Business context for better communication style
        user_message: The user's last message for context
        conversation_context: Recent conversation history for context
    """
    instr = instruction or DEFAULT_INSTRUCTION

    # Add project context to instruction if available
    if project_context and project_context.has_rewriter_context():
        context_prompt = project_context.get_rewriter_context_prompt()
        instr = f"{instr}\n{context_prompt}"

    # Build context-aware input for the LLM
    llm_input = f"Texto para naturalizar: {text}"
    
    if user_message:
        llm_input += f"\n\nÚltima mensagem do usuário: {user_message}"
    
    if conversation_context:
        recent_msgs = conversation_context[-3:]  # Last 3 messages for context
        context_str = "\n".join(f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in recent_msgs)
        llm_input += f"\n\nContexto da conversa:\n{context_str}"

    try:
        rewritten = llm.rewrite(instr, llm_input)
        
        # Log the prompt and response
        prompt_logger.log_prompt(
            prompt_type="naturalize_single",
            instruction=instr,
            input_text=llm_input,
            response=rewritten if isinstance(rewritten, str) else str(rewritten),
            model=getattr(llm, 'model_name', 'unknown'),
            metadata={"has_project_context": project_context is not None}
        )
        
        if isinstance(rewritten, str) and rewritten.strip():
            # Defensive sanitization to ensure single-line question
            first_line = next((ln.strip() for ln in rewritten.splitlines() if ln.strip()), "")
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if first_line.startswith('"') and first_line.endswith('"') and len(first_line) > 1:
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
            model=getattr(llm, 'model_name', 'unknown'),
            metadata={"error": str(e)}
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

    # Add project context to instruction if available
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
            model=getattr(llm, 'model_name', 'unknown'),
            metadata={"has_project_context": project_context is not None}
        )
        
        if isinstance(rewritten, str) and rewritten.strip():
            first_line = next((ln.strip() for ln in rewritten.splitlines() if ln.strip()), "")
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if first_line.startswith('"') and first_line.endswith('"') and len(first_line) > 1:
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
            model=getattr(llm, 'model_name', 'unknown'),
            metadata={"error": str(e)}
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
    last_user_message: str = ""
    for turn in chat_window or []:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()
        if role and content:
            history_lines.append(f"{role}: {content}")
            if role.lower() == "user":
                last_user_message = content

    history_block = "\n".join(history_lines[-200:])  # cap to keep prompt bounded

    instruction = (
        "Você é uma recepcionista brasileira profissional mas muito calorosa no WhatsApp. Imagine uma recepcionista exemplar - "
        "competente, simpática, acolhedora, que as pessoas adoram ser atendidas por ela, mas sempre mantém profissionalismo.\n\n"
        "ANÁLISE CONTEXTUAL (FAÇA ISSO PRIMEIRO):\n"
        "Antes de responder, analise profundamente:\n"
        "1. O tom emocional da última mensagem do usuário (animado? confuso? neutro? frustrado? curioso?)\n"
        "2. O contexto da conversa até agora (primeira interação? já conversaram? qual o assunto?)\n"
        "3. O tipo de resposta necessária (informação? confirmação? escolha? esclarecimento?)\n"
        "4. A complexidade da resposta (simples = 1 msg, média = 2 msgs, complexa = 3+ msgs)\n\n"
        "PERSONALIDADE PROFISSIONAL CALOROSA:\n"
        "Adapte sua resposta baseado no contexto:\n"
        "- Usuário animado → Seja cordial e positiva: 'Que ótimo!', 'Perfeito!', 'Excelente!'\n"
        "- Usuário confuso → Seja paciente e clara: 'Sem problemas, vou esclarecer', 'Claro, deixa eu explicar'\n"
        "- Usuário neutro → Seja profissional mas calorosa: 'Claro', 'Perfeito', 'Vamos lá'\n"
        "- Usuário apressado → Seja eficiente mas gentil: 'Certo, vamos direto ao ponto'\n"
        "- Primeira interação → Seja acolhedora mas profissional: 'Olá! Como posso ajudar?'\n\n"
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
        "TÉCNICAS DE NATURALIDADE PROFISSIONAL:\n"
        "- Varie inícios cordiais: 'Perfeito!', 'Ótimo!', 'Certo!', 'Claro!', 'Beleza!', ou direto na pergunta\n"
        "- Use reticências com moderação: 'então...', 'é que...', quando apropriado\n"
        "- Emojis moderados e profissionais: 😊 (gentileza), quando fizer sentido no contexto\n"
        "- Interjeições suaves: 'né?', 'certo?', quando couber naturalmente\n"
        "- Expressões brasileiras cordiais: 'que bom', 'perfeito', 'excelente', 'tranquilo'\n\n"
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
        "Formato: JSON array [{\"text\": string, \"delay_ms\": number}]\n"
        "Delays: primeira sempre 0, outras entre 2200-3800ms (varie para parecer natural)\n"
        "Tamanho: máximo 150 caracteres por mensagem, mas varie (algumas bem curtas como 'Perfeito!' outras maiores)\n"
    )

    # Add project context to instruction if available
    if project_context and project_context.has_rewriter_context():
        context_prompt = project_context.get_rewriter_context_prompt()
        instruction = f"{instruction}\n{context_prompt}"

    payload = (
        f"Original assistant reply:\n{original_text}\n\n"
        f"Latest user message (if any):\n{last_user_message}\n\n"
        f"Conversation window (oldest to newest):\n{history_block}"
    )

    try:
        raw = llm.rewrite(instruction, payload)
        
        # Log the prompt and response
        prompt_logger.log_prompt(
            prompt_type="whatsapp_multi",
            instruction=instruction,
            input_text=payload,
            response=raw if isinstance(raw, str) else str(raw),
            model=getattr(llm, 'model_name', 'unknown'),
            metadata={
                "has_project_context": project_context is not None,
                "max_followups": max_followups,
                "last_user_message": last_user_message
            }
        )
        
        # Try to parse JSON array
        import json

        messages = json.loads(raw) if isinstance(raw, str) else []
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
