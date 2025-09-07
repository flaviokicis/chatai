from __future__ import annotations

from typing import TYPE_CHECKING

from langfuse import get_client
from .prompt_logger import prompt_logger

if TYPE_CHECKING:  # avoid hard import at runtime
    from app.services.tenant_config_service import ProjectContext

    from .llm import LLMClient

# Human pacing defaults for multi-message outputs
MIN_FOLLOWUP_DELAY_MS = 2200
MAX_FOLLOWUP_DELAY_MS = 4000
MAX_MULTI_MESSAGES = 8

# This constant is now deprecated - kept for reference but not used
# The base instructions are now embedded in the _build_base_instruction function
DEFAULT_INSTRUCTION_DEPRECATED = ""

def _build_base_instruction(is_completion: bool = False) -> str:
    """
    Build the base instruction that is always used, regardless of custom communication style.
    This contains all the fundamental rules for naturalization.
    
    Args:
        is_completion: Whether this is the final message/completion of the conversation flow
    """
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
    
    return (
        f"{completion_context}"
        "CONTEXTO CRÍTICO - CONVERSA WHATSAPP EM ANDAMENTO:\n"
        "- Você está no MEIO de uma conversa WhatsApp que já está acontecendo\n"
        "- Quando fizer sentido, tente conectar com a(s) última(s) mensagem(s) brevemente, sempre variando o estilo.\n"
        "- O usuário e você já trocaram mensagens (veja o histórico)\n"
        "- NÃO trate cada mensagem como um novo início - é uma CONTINUAÇÃO\n"
        "- Mantenha a fluidez natural de um chat WhatsApp brasileiro\n\n"
        "OBJETIVO GERAL:\n"
        "- Continue a conversa de forma calorosa e natural\n"
        "- A mensagem original é apenas uma DIREÇÃO - reescreva completamente\n"
        "- Crie uma comunicação que soe como a continuação natural do papo\n"
        "- Reescreva em 1 a 3 mensagens mantendo o flow da conversa\n"
        "- Preserve a INTENÇÃO, mas use suas próprias palavras naturais\n"
        "- A última mensagem deve sempre direcionar para o próximo passo\n"
        "- NUNCA faça suposições - baseie-se no que foi dito\n\n"
        
        "REGRA FUNDAMENTAL - PRESERVE A INTENÇÃO, NÃO AS PALAVRAS:\n"
        "- A mensagem original indica QUAL informação buscar ou comunicar - use isso como direção\n"
        "- Você tem LIBERDADE CRIATIVA total para expressar essa intenção de forma natural\n"
        "- JAMAIS adicione NOVOS TÓPICOS que não estão na intenção original\n"
        "- Se a intenção é perguntar sobre PLANO DE SAÚDE → pergunte sobre isso (mas do seu jeito)\n"
        "- Se a intenção é saber DISPONIBILIDADE → descubra isso (mas naturalmente)\n"
        "- Use o histórico apenas para entender contexto, JAMAIS para copiar conteúdo\n"
        "- IGNORE completamente o Business Context - ele NÃO é parte da conversa\n"
        "- Business Context é apenas para você entender que empresa representa\n"
        "- NUNCA assuma interesse do usuário baseado no que a empresa faz\n"
        "- Só porque a empresa vende algo não significa ainda que o usuário quer tal algo sem que ele diga\n"
        "- NÃO REPITA capacidades da empresa (experiência, qualidade, etc.) se já foram mencionadas\n\n"
        
        "ANÁLISE CONTEXTUAL (FAÇA ISSO PRIMEIRO):\n"
        "Antes de responder, analise profundamente:\n"
        "1. O tom emocional da última mensagem do usuário (animado? confuso? neutro? frustrado? curioso?)\n"
        "2. O contexto da conversa até agora (primeira interação? já conversaram? qual o assunto?)\n"
        "3. O tipo de resposta necessária (informação? confirmação? escolha? esclarecimento?)\n"
        "4. A complexidade da resposta (simples = 1 msg, média = 2 msgs, complexa = 3+ msgs)\n"
        "5. CRÍTICO: Se já houve saudação anterior → NÃO cumprimente de novo, vá direto ao assunto\n"
        "6. CONTE quantas vezes você já falou → varie completamente o estilo a cada resposta\n"
        "7. LISTE mentalmente O QUE JÁ FOI DITO → NUNCA repita esses fatos/acknowledgments\n"
        "8. SE O USUÁRIO FEZ UMA PERGUNTA DE CLARIFICAÇÃO (sobre formato, unidades, como responder):\n"
        "   - RESPONDA DIRETAMENTE à pergunta primeiro (ex: 'Sim, pode ser dessa forma!')\n"
        "   - Depois continue com a pergunta original de forma natural\n"
        "   - NÃO comece com saudações desconexas como 'E aí!' após uma pergunta específica, a conversa precisa manter a fluidez natural\n\n"
        
        "EXEMPLOS DO QUE NÃO FAZER:\n"
        "❌ Primeira msg: 'Olá!' Segunda msg: 'Claro!' Terceira: 'Poxa!' → REPETITIVO\n"
        "❌ Começar toda resposta com acknowledgment: 'Claro!', 'Legal!', 'Entendi!' → ROBÓTICO\n"
        "❌ Msg 1: 'Legal sua quadra de tênis!' → Msg 2: 'Que bacana sua quadra!' → REDUNDANTE\n"
        "❌ Msg 1: 'Temos experiência!' → Msg 2: 'Somos experientes!' → REPETINDO FATOS\n"
        "❌ Usuário: 'Olá' → Você: 'Vejo que tem interesse em LED!' → INVENTANDO FATOS\n"
        "❌ Adicionar 'Que legal!' ou 'Vejo que...' sobre coisas não mencionadas → FABRICAÇÃO\n"
        "❌ Responder dúvidas sobre informações que não foram fornecidas → FABRICAÇÃO\n"
        "❌ Responder dúvidas que não fazem parte do escopo da conversa → FABRICAÇÃO\n"
        "✅ Primeira msg: saudação + pergunta direta → Segunda: nova info → Terceira: próximo passo\n"
        "✅ Se não sabe algo, PERGUNTE - não invente ou assuma\n\n"
        
        "ADAPTAÇÃO CONTEXTUAL:\n"
        "- Adapte o tom baseado no contexto da conversa\n"
        "- Mantenha consistência com o padrão estabelecido\n"
        "- Seja natural sem exageros\n\n"
        
        "ESTRATÉGIA DE MENSAGENS PROGRESSIVA:\n"
        "USE O HISTÓRICO para decidir como responder:\n\n"
        "• DETECTE O ESTÁGIO DA CONVERSA:\n"
        "  - Se há múltiplas mensagens do usuário no histórico → NÃO é a primeira interação\n"
        "  - Se o usuário já forneceu informações específicas → conversa em andamento\n"
        "  - Se o usuário está fazendo perguntas de clarificação → responda diretamente\n\n"
        "• CONTINUIDADE NATURAL NO WHATSAPP:\n"
        "  - SE há mensagens anteriores no histórico: você está continuando a conversa\n"
        "  - SE o histórico está vazio ou só tem 'Olá/Oi': pode ser a primeira interação\n"
        "  - Mantenha o tom caloroso e brasileiro mas adapte ao momento da conversa\n\n"
        "• QUANDO USAR SAUDAÇÕES (RARO):\n"
        "  - APENAS na primeira mensagem quando o usuário disse somente 'Olá'\n"
        "  - Depois disso, NUNCA MAIS use 'E aí!', 'Olá!', 'Oi!' etc.\n\n"
        "• COMO MANTER O CALOR HUMANO SEM SAUDAÇÕES:\n"
        "  - Use expressões naturais: 'Ah, entendi!', 'Perfeito!', 'Show!'\n"
        "  - Demonstre interesse: 'Que legal, campo de futebol!'\n"
        "  - Seja empático: 'Imagino que...', 'Deve ser...'\n"
        "  - Mas SEMPRE avance a conversa - não fique só comentando\n\n"
        "• EXEMPLOS DE BOA CONTINUIDADE:\n"
        "  - Após correção: 'Ah, campo de futebol! Perfeito! Me conta então...'\n"
        "  - Após clarificação: 'Sim, pode ser em metros! Então, qual o tamanho do campo?'\n"
        "  - Mudança de contexto: 'Entendi, vamos falar do campo então! Preciso saber...'\n\n"
        "• PROGRESSÃO NATURAL:\n"
        "  - Mantenha continuidade: cada resposta deve fluir naturalmente da anterior\n"
        "  - NÃO reinicie a conversa com saudações após perguntas específicas\n"
        "  - SEMPRE considere o contexto imediato da última mensagem do usuário\n\n"
        
        "ORDEM OBRIGATÓRIA DAS MENSAGENS:\n"
        "- PRIMEIRA(S) mensagem(ns): Reconhecimentos, confirmações, saudações, comentários\n"
        "- ÚLTIMA mensagem: SEMPRE a pergunta principal que drive a conversa\n"
        "- A pergunta que solicita informação do usuário DEVE ser a última mensagem\n"
        "- Cada mensagem deve focar na INTENÇÃO PRINCIPAL da mensagem original\n"
        "- Mantenha coerência: todas as mensagens devem trabalhar para o mesmo objetivo\n\n"
        
        "USE O HISTÓRICO INTELIGENTEMENTE - NUNCA REPITA:\n"
        "- ANALISE o histórico para entender O QUE JÁ FOI DITO - NUNCA repita informações\n"
        "- Se já reconheceu 'quadra de tênis' → NUNCA mencione novamente que ele tem quadra de tênis\n"
        "- Se já disse que tem experiência → NÃO repita sobre experiência\n"
        "- PROGRESSÃO OBRIGATÓRIA: Cada resposta deve adicionar NOVA informação, não reciclar\n"
        "- PROIBIDO: Re-acknowledgar informações já processadas (ex: 'que legal sua quadra' duas vezes)\n"
        "- Se o usuário já forneceu uma informação → ASSUMA como conhecido e siga em frente\n"
        "- Use o histórico para EVITAR redundâncias - se algo foi dito, está dito\n"
        "- PRESERVE A INTENÇÃO da mensagem original, mas SEMPRE avance a conversa\n"
        "- Exemplo RUIM: 'Legal sua quadra!' → próxima msg: 'Que bacana sua quadra!'\n"
        "- Exemplo BOM: 'Legal sua quadra!' → próxima msg: direto para próxima informação\n"
        
        "TÉCNICAS DE NATURALIDADE PROFISSIONAL:\n"
        "- Varie inícios cordiais naturalmente\n"
        "- Use elementos do português brasileiro com moderação\n"
        "- Mantenha tom profissional mas caloroso\n"
        "- Adapte-se ao estilo sem repetir sempre as mesmas expressões\n\n"
        
        "SAUDAÇÕES E ACKNOWLEDGMENTS - REGRA CRÍTICA:\n"
        "- PROIBIDO usar saudações ('E aí!', 'Olá!', 'Oi!') após a primeira mensagem\n"
        "- Se o usuário JÁ forneceu QUALQUER informação específica → ZERO saudações\n"
        "- 'Claro!', 'Poxa!', 'Legal!', 'Entendi!', 'Com certeza!' = SAUDAÇÕES DISFARÇADAS - evite\n"
        "- Após primeira interação → VÁ DIRETO AO PONTO, sem introduções ou preâmbulos\n"
        "- IGNORE saudações/acknowledgments no ack_message ou tool context - não as repita\n"
        "- Única exceção: primeira mensagem quando usuário disse apenas 'Olá'\n\n"
        
        "TOM NATURAL (SEM MULETAS):\n"
        "- PALAVRAS PROIBIDAS no início (após 1ª msg): 'Claro!', 'Poxa!', 'Legal!', 'Entendi!', 'Certo!', 'Ok!', 'Com certeza!', 'Ótimo!', 'Perfeito!'\n"
        "- Após primeira mensagem, vá DIRETO ao conteúdo sem introduções\n"
        "- Seja direto e natural - não precisa de preâmbulos educados a cada resposta\n"
        "- Se você já usou 'Claro' uma vez → NUNCA mais use na conversa\n"
        
        "COESÃO COM A CONVERSA:\n"
        "- Quando repetir uma pergunta porque o usuário pediu esclarecimento ou fez outra pergunta,\n"
        "  você PODE adicionar UMA frase breve e empática. Você pode alterar a frase conforme a necessidade para seguir e integrar com a conversa, sem que altere o rumo da conversa.\n"
        
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
        
        "REGRA OBRIGATÓRIA - PERGUNTAS DEVEM CONTINUAR SENDO PERGUNTAS:\n"
        "- Se a INTENÇÃO original é obter informação → sua naturalização DEVE buscar essa informação\n"
        "- Se o texto original é uma PERGUNTA → mantenha a natureza interrogativa (mas reescreva livremente) e termine a interação com uma pergunta que responde a pergunta original.\n"
        "- A pergunta pode ser TOTALMENTE diferente em palavras, mas deve buscar a MESMA INFORMAÇÃO\n"
        "- Exemplo: 'Qual o seu numero de telefone?' → 'Ah, e qual seria o melhor número pra te encontrar?'\n"
        "- JAMAIS transforme pergunta em afirmação - sempre mantenha conversa fluindo pra completar os objetivos.\n\n"
        
        "EVITE MAIS DE UMA OU DUAS PERGUNTAS EM UMA MENSAGEM OU TURNO. Mesmo que a pergunta seja curta. Muitas interrogações podem ser chamativas e desagradáveis.\n\n"
        
        "NAO USE MAIS DE UMA SAUDACAO, POR EXEMPLO 'E AÍ' ou 'Olá', POR CONVERSA.\n"
        
        'Formato: JSON array [{"text": string, "delay_ms": number}]\n'
        "Delays: primeira sempre 0, outras entre 2200-3800ms (varie para parecer natural)\n"
        "Tamanho: máximo 150 caracteres por mensagem, mas varie (algumas bem curtas como 'Perfeito!' outras maiores)\n"
    )


def _get_tool_description_pt(tool_name: str) -> str:
    """Extrai a descrição da ferramenta diretamente dos schemas definidos."""
    try:
        # Import the tool schemas to get the actual docstrings
        from app.flow_core.tool_schemas import FLOW_TOOLS, UnknownAnswer, ModifyFlowLive
        
        # Add additional tools to the search list
        all_tools = FLOW_TOOLS + [UnknownAnswer, ModifyFlowLive]
        
        # Find the tool class by name
        for tool_class in all_tools:
            if tool_class.__name__ == tool_name:
                # Get the docstring and clean it up
                docstring = tool_class.__doc__
                if docstring:
                    # Return cleaned full docstring to preserve important usage rules
                    return docstring.strip()
        
        # Fallback: return empty string if tool not found
        return ""
    except Exception:
        # Fallback: return empty string if import fails
        return ""

def rewrite_whatsapp_multi(
    llm: LLMClient,  # type: ignore[name-defined]
    original_text: str,
    chat_window: list[dict[str, str]] | None = None,
    *,
    max_followups: int = 2,
    project_context: ProjectContext | None = None,  # type: ignore[name-defined]
    is_completion: bool = False,
    tool_context: dict[str, str] | None = None,
    current_time: str | None = None,
) -> list[dict[str, int | str]]:
    """Rewrite an assistant reply into human-like WhatsApp-style messages.

    Returns a list of {"text": str, "delay_ms": int} objects. The first message should have
    delay_ms=0. Follow-ups should be paced to feel human.

    Args:
        is_completion: Whether this is the final message/completion of the conversation flow
        tool_context: Optional context about the tool/action that was executed, with keys like 'tool_name' and 'description'
        current_time: Current time in HH:MM format to match conversation timestamps

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
        timestamp = turn.get("timestamp", "")
        
        if role and content:
            # Add timestamp and role for better context  
            sequence = i + 1
            if timestamp:
                history_lines.append(f"[{timestamp}] {role}: {content}")
            else:
                history_lines.append(f"[{sequence}] {role}: {content}")

    # Take last 10 turns and ensure chronological order (oldest first)
    recent_history = history_lines[-10:] if history_lines else []
    history_block = "\n".join(recent_history) if recent_history else "No previous conversation"

    # Build the instruction with the new consolidated approach
    # Step 1: Always start with the base instruction
    instruction = _build_base_instruction(is_completion=is_completion)
    
    # Step 2: If custom communication style is provided, add it as a priority layer
    if project_context and project_context.communication_style:
        custom_style_overlay = (
            "\n=== ESTILO DE COMUNICAÇÃO CUSTOMIZADO DO CLIENTE (PRIORIDADE) ===\n"
            "IMPORTANTE: O cliente forneceu um estilo de comunicação específico que deve ser PRIORIZADO.\n"
            "Aplique este estilo mantendo as regras fundamentais acima sobre preservação de conteúdo.\n\n"
            f"ESTILO DO CLIENTE:\n{project_context.communication_style}\n\n"
            "COMO APLICAR:\n"
            "• Este estilo tem PRIORIDADE sobre o tom padrão brasileiro\n"
            "• Absorva o TOM, PERSONALIDADE e LINGUAGEM do estilo do cliente\n"
            "• Aplique esse estilo naturalmente à sua mensagem\n"
            "• MANTENHA sempre o assunto da mensagem original\n"
            "• Varie as expressões - não copie frases específicas literalmente\n"
            "• Preserve todas as outras regras fundamentais sobre conteúdo e estrutura\n"
            "• CRÍTICO: Aplique TODAS as regras sobre saudações - nunca repita 'olá', 'oi', etc. após primeira vez que você já mandou uma saudação a nao ser que seja a primeira mensagem da conversa ou depois de muito tempo sem interação\n\n"
        )
        instruction = instruction + custom_style_overlay
    else:
        # Add default Brazilian style clarification when no custom style
        default_style_note = (
            "\n=== TOM PADRÃO (quando não há estilo customizado) ===\n"
            "- Profissional mas calorosa\n"
            "- Natural e brasileira\n"
            "- Simpática mas respeitosa\n"
            "- Use contrações naturais: 'tá', 'pra', 'né', mas com moderação\n"
            "- Finalize cordialmente: '?' simples, 'certo?', ou sem nada\n"
            "- Evite tanto formalidade excessiva quanto casualidade demais\n"
            "- Tom: como uma recepcionista que você adora conversar mas que é competente\n\n"
        )
        instruction = instruction + default_style_note
    
    # Gate Business Context injection (tool-agnostic):
    # - Only for completions OR when the original text is NOT a short/neutral question
    # - Avoid injecting for simple questions to prevent domain leakage
    is_question = bool((original_text or "").strip().endswith("?"))
    should_inject_bc = False
    if project_context and project_context.has_rewriter_context() and not project_context.communication_style:
        if is_completion:
            should_inject_bc = True
        elif (not is_question) and len((original_text or "").strip()) >= 80:
            should_inject_bc = True
    if should_inject_bc:
        try:
            context_prompt = project_context.get_rewriter_context_prompt()
            instruction = f"{instruction}\n{context_prompt}"
        except Exception:
            pass

    history_block = "\n".join(history_lines[-200:])  # cap to keep prompt bounded
    
    # Build tool context section if provided
    tool_context_section = ""
    # Extract ack message early for fallback usage
    ack_message_txt = ""
    if isinstance(tool_context, dict):
        ack_message_txt = str(tool_context.get("ack_message", "") or "").strip()
    if tool_context and tool_context.get("tool_name"):
        tool_name = tool_context.get("tool_name", "")
        tool_description = _get_tool_description_pt(tool_name)
        ack_hint = tool_context.get("ack_message", "") if isinstance(tool_context, dict) else ""
        if tool_description:
            tool_context_section = f"""
=== AÇÃO EXECUTADA (para contexto da comunicação) ===
Ferramenta utilizada: {tool_name}
Descrição técnica: {tool_description}

Se estiver repetindo a pergunta por causa do contexto acima, você PODE usar uma frase curta e empática
para manter a conversa natural antes de refazer a pergunta (ex.: "Claro!", "Sem problemas!").
"""
            if ack_hint:
                tool_context_section += f"""
Sugestão breve (contexto): {ack_hint}

"""
            tool_context_section += """
IMPORTANTE: Esta informação é apenas para você entender o CONTEXTO da ação que acabou de acontecer.
Use isso para comunicar de forma mais natural e contextual, mas SEMPRE preserve o conteúdo da mensagem original.
A descrição pode estar em inglês, mas sua resposta deve sempre ser no estilo do cliente.

"""
    
    # Add current time context if provided
    time_context_section = ""
    if current_time:
        time_context_section = f"""
=== CONTEXTO TEMPORAL ===
Horário atual: {current_time}

IMPORTANTE: Use esta informação para adaptar saudações e referências temporais de forma natural.
Exemplo: se for manhã use "bom dia", se for tarde use "boa tarde", etc.

"""

    # Conditionally include business context section (tool-agnostic)
    business_section = ""
    if should_inject_bc and project_context and project_context.project_description:
        business_section = f"""
=== BUSINESS CONTEXT (for company understanding only) ===
Business: {project_context.project_description}

"""

    payload = f"""=== ORIGINAL MESSAGE TO REWRITE ===
{original_text}

=== CONVERSATION HISTORY SO FAR ===
(CRÍTICO: Use para entender ONDE você está na conversa e VARIAR seu estilo a cada resposta)
(CONTE quantas vezes já respondeu e varie a abordagem - sem repetir padrões)
{history_block}
{tool_context_section}{time_context_section}{business_section}=== INSTRUÇÕES CRÍTICAS ===
1. Use "Original message to rewrite" APENAS para entender a INTENÇÃO
2. Você tem LIBERDADE TOTAL para reescrever completamente - pode ser 100% diferente em palavras
3. O contexto de negócio é só para você saber que empresa representa (quando presente)
4. NÃO adicione NOVOS TÓPICOS que não estão na intenção original
5. NÃO trate o contexto de negócio como parte da conversa
6. Preserve apenas a INTENÇÃO e OBJETIVO - as palavras podem ser totalmente diferentes
7. NUNCA re-acknowledge informações já processadas (quadra de tênis, experiência, etc.)
8. Cada resposta deve AVANÇAR a conversa, não reciclar conteúdo anterior

=== SUA TAREFA ===
Pegue a INTENÇÃO da mensagem original e expresse-a de forma completamente natural e conversacional.
Não se prenda às palavras originais - crie uma comunicação genuinamente humana e calorosa.
CRÍTICO: NÃO invente fatos! Se o usuário não disse ter interesse em algo, NÃO diga "vejo que tem interesse".
LEMBRE-SE: Após primeira mensagem, NUNCA comece com 'Claro!', 'Poxa!', 'Legal!' - vá direto ao ponto!
"""

    # Start Langfuse generation with cost tracking
    langfuse_client = get_client()
    generation = langfuse_client.start_observation(
        name="whatsapp_naturalization",
        as_type="generation",
        model=getattr(llm, "model_name", "unknown"),
        input=payload,
        metadata={
            "operation": "text_naturalization",
            "style": "whatsapp_multi",
            "has_project_context": project_context is not None,
            "is_completion": is_completion,
            "max_followups": max_followups,
            "original_text_length": len(original_text),
            "instruction_length": len(instruction),
        }
    )

    try:
        # Use a dedicated lightweight model for naturalization/rewriting
        from langchain.chat_models import init_chat_model
        rewrite_chat = init_chat_model("gemini-2.5-flash-lite", model_provider="google_genai")
        
        # Tool-agnostic greeting suppression using chat history
        def _strip_redundant_greeting(text: str, history: list[dict[str, str]] | None) -> str:
            try:
                if not text or not history:
                    return text
                last_assistant = None
                for turn in reversed(history):
                    role = (turn.get("role") or "").lower()
                    if role in ("assistant", "ai"):
                        last_assistant = (turn.get("content") or "").strip().lower()
                        break
                if not last_assistant:
                    return text
                greeting_tokens = ["olá", "oi", "boa tarde", "bom dia", "boa noite"]
                lower = text.strip()
                for g in greeting_tokens:
                    if lower.lower().startswith(g):
                        import re as _re
                        stripped = _re.sub(rf"^({g}[!.,\s]*)", "", lower, flags=_re.IGNORECASE)
                        if stripped:
                            return stripped.lstrip()
                return text
            except Exception:
                return text

        safe_original = _strip_redundant_greeting(original_text, chat_window)
        payload = payload.replace(original_text, safe_original)

        full_prompt = f"{instruction}\n\n{payload}"
        result = rewrite_chat.invoke(full_prompt)
        raw = getattr(result, "content", original_text) or original_text

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

            # Tool-agnostic polish: remove stiff leading fillers and keep concise for questions
            try:
                import re as _re
                if out:
                    first_text = str(out[0].get("text", ""))
                    first_text = _re.sub(
                        r"^(?:entendido|entendi|certo|ok|perfeito|beleza|tranquilo|combinado)[!.,\s:\-–—]*",
                        "",
                        first_text,
                        flags=_re.IGNORECASE,
                    ).lstrip()
                    out[0]["text"] = first_text or out[0].get("text", "")
                # If original was a simple question, prefer at most two bubbles (clarifier + question)
                is_question = bool((original_text or "").strip().endswith("?"))
                if is_question and len(out) > 2:
                    out = [out[0], out[-1]]
            except Exception:
                pass
            
            # Update generation with successful result
            generation.update(
                output=json.dumps(out),
                metadata={
                    "messages_generated": len(out),
                    "total_characters": sum(len(str(msg.get("text", ""))) for msg in out),
                    "json_parsed_successfully": True,
                }
            )
            generation.end()
            return out
    except Exception as e:
        # Update generation with error
        generation.update(
            output=json.dumps([{"text": original_text, "delay_ms": 0}]),
            metadata={
                "error": str(e),
                "fallback_used": True,
                "error_type": type(e).__name__,
            }
        )
        generation.end()

    # Fallback: if LLM fails, use ack_message (if provided) then the original text
    if ack_message_txt:
        fallback_msgs: list[dict[str, int | str]] = [
            {"text": ack_message_txt, "delay_ms": 0}
        ]
        # Ensure a follow-up bubble with the question/content
        safe_text = (original_text or "").strip()
        if safe_text:
            fallback_msgs.append({"text": safe_text, "delay_ms": MIN_FOLLOWUP_DELAY_MS})
        return fallback_msgs

    # Simple fallback: if no ack available, return original text as-is
    return [{"text": original_text, "delay_ms": 0}]



