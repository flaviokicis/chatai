from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid hard import at runtime
    from app.services.tenant_config_service import ProjectContext

    from .llm import LLMClient

# Human pacing defaults for multi-message outputs
MIN_FOLLOWUP_DELAY_MS = 2200
MAX_FOLLOWUP_DELAY_MS = 4000
MAX_MULTI_MESSAGES = 8

DEFAULT_INSTRUCTION = (
    "Você é uma atendente brasileira no WhatsApp. Reescreva o prompt em uma frase única, natural e casual em português (Brasil),"
    " com tom caloroso e do dia a dia. Regras: uma frase; sem listas; sem aspas; mantenha o significado; conciso;"
    " reconheça sutilmente a última fala do usuário quando fizer sentido (ex.: 'entendi', 'claro')."
)


def naturalize_prompt(
    llm: LLMClient,  # type: ignore[name-defined]
    text: str,
    instruction: str | None = None,
    project_context: ProjectContext | None = None,  # type: ignore[name-defined]
) -> str:
    """
    Naturalize a prompt for WhatsApp with optional project context.

    Args:
        llm: LLM client for rewriting
        text: Original text to rewrite
        instruction: Custom instruction (overrides default)
        project_context: Business context for better communication style
    """
    instr = instruction or DEFAULT_INSTRUCTION

    # Add project context to instruction if available
    if project_context and project_context.has_rewriter_context():
        context_prompt = project_context.get_rewriter_context_prompt()
        instr = f"{instr}\n{context_prompt}"

    try:
        rewritten = llm.rewrite(instr, text)
        if isinstance(rewritten, str) and rewritten.strip():
            # Defensive sanitization to ensure single-line question
            first_line = next((ln.strip() for ln in rewritten.splitlines() if ln.strip()), "")
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if first_line.startswith('"') and first_line.endswith('"') and len(first_line) > 1:
                first_line = first_line[1:-1].strip()
            return first_line or text
        return text
    except Exception:
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
        "Papel: atendente brasileira no WhatsApp. O usuário pediu esclarecimento. "
        "Faça um breve reconhecimento citando de leve a fala do usuário (ex.: 'ah, entendi', 'claro'), "
        "e emende a pergunta original de forma natural e curta. "
        "Uma única frase; sem listas; sem aspas; muito natural e do dia a dia; tom leve."
    )

    # Add project context to instruction if available
    if project_context and project_context.has_rewriter_context():
        context_prompt = project_context.get_rewriter_context_prompt()
        instr = f"{instr}\n{context_prompt}"

    try:
        text = f"Pergunta: {question_text}\nUsuário perguntou: {user_message}"
        rewritten = llm.rewrite(instr, text)
        if isinstance(rewritten, str) and rewritten.strip():
            first_line = next((ln.strip() for ln in rewritten.splitlines() if ln.strip()), "")
            if first_line.startswith(("- ", "* ")):
                first_line = first_line[2:].strip()
            if first_line.startswith('"') and first_line.endswith('"') and len(first_line) > 1:
                first_line = first_line[1:-1].strip()
            return first_line
        return question_text
    except Exception:
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
        "Papel: você é uma assistente virtual de IA brasileira, calorosa e amigável no WhatsApp.\n"
        "Tarefa: reescreva a resposta do assistente em mensagens curtas e naturais, soando como uma pessoa de verdade.\n"
        "Você decide quantas mensagens enviar (uma é ok; duas às vezes funcionam melhor).\n\n"
        "REGRAS DE SIGNIFICADO (obrigatórias):\n"
        "- Preserve o significado original. Não mude o tópico nem invente detalhes.\n"
        "- Quando houver opções, mantenha os substantivos essenciais (ex.: 'quadra/tênis', 'campo/futebol', 'galpão').\n"
        "- Evite tom de menu. NÃO use 'escolha uma opção', 'selecione', nem enumeração com números.\n"
        "- Você pode reformular levemente a pergunta para ficar natural, desde que as opções apareçam como exemplos em uma única frase.\n"
        "- Não adicione novas opções; não remova opções importantes.\n\n"
        "ENERGIA E TOM (espelhar o usuário):\n"
        "- Observe a última fala do usuário e espelhe a ENERGIA.\n"
        "  * Se for animada (ex.: muitas exclamações, 'olaaaa', emojis), use um reconhecimento curto e animado (ex.: 'Opa!' ou 'Claro!') e 0-1 exclamações.\n"
        "  * Se for neutra/formal, mantenha direto e simples (sem exclamações).\n"
        "  * Pode usar emoji; mas sem exagerar 🙂.\n"
        "- Não force empolgação se o usuário estiver formal.\n\n"
        "Diretrizes de estilo:\n"
        "- Comece com um reconhecimento breve que faça referência à fala do usuário quando fizer sentido.\n"
        "- Faça a pergunta de forma simples e livre (ex.: 'é mais pra X, Y, Z ou algo diferente?').\n"
        "- Sem listas ou bullets. Uma pergunta direta em tom de conversa.\n"
        "- Mantenha cada mensagem com <= 120 caracteres.\n"
        "- Evite repetir saudações.\n"
        "- Tempo: primeira mensagem delay_ms = 0; seguintes entre 2200-4000 ms.\n\n"
        "Identidade (quando perguntarem 'você é IA?'):\n"
        "- Responda antes com: 'Sou uma assistente virtual de IA e estou aqui para te ajudar.' e depois continue normalmente.\n\n"
        "Saída ESTRITAMENTE como um array JSON de {text: string, delay_ms: integer}.\n\n"
        "Exemplos (apenas formato; adapte o tom):\n"
        "Entrada: 'Com base na descrição do usuário, escolha o melhor caminho: quadra/tênis, campo/futebol, galpão ou outros.'\n"
        '[\n  {"text": "Opa!", "delay_ms": 0},\n  {"text": "é mais pra quadra/tênis, campo/futebol, galpão ou algo diferente?", "delay_ms": 2400}\n]\n\n'
        "Entrada: 'É em ambiente interno (indoor) ou externo (outdoor)?'\n"
        '[\n  {"text": "É em ambiente interno (indoor) ou externo (outdoor)?", "delay_ms": 0}\n]\n\n'
        "Entrada (formal): 'Com o que posso te ajudar hoje?'\n"
        '[\n  {"text": "Como posso te ajudar hoje?", "delay_ms": 0}\n]\n\n'
        "Importante: escreva as mensagens em português (Brasil)."
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

    # Deterministic fallback: if the text looks like a menu/decision, rephrase into natural question
    def _deterministic_menu_fallback(
        text: str, last_user: str | None
    ) -> list[dict[str, int | str]] | None:
        lower = text.lower()
        has_menu_signal = (
            "caminho" in lower or "escolha" in lower or "qual caminho" in lower
        ) and ("quadra" in lower or "futebol" in lower or "galp" in lower)
        if not has_menu_signal:
            return None
        # Try to extract options after a colon
        options_part = None
        if ":" in text:
            try:
                options_part = text.split(":", 1)[1].strip()
            except Exception:
                options_part = None
        # Clean punctuation
        if options_part:
            if options_part.endswith("."):
                options_part = options_part[:-1].strip()
        # Build messages
        out: list[dict[str, int | str]] = []
        if last_user and last_user.strip():
            out.append({"text": "Certo!", "delay_ms": 0})
            second_delay = MIN_FOLLOWUP_DELAY_MS
        else:
            second_delay = 0
        question_body = (
            f"é mais pra {options_part}?" if options_part else "por qual tipo a gente segue?"
        )
        out.append({"text": question_body, "delay_ms": second_delay})
        return out

    det = _deterministic_menu_fallback(original_text, last_user_message or None)
    if det:
        return det

    # Final fallback: return the original text verbatim
    # Lightly mirror user energy in a tiny acknowledgment if very enthusiastic
    try:
        last = (last_user_message or "").strip()
        high_energy = (
            last.count("!") >= 2 or "olaaa" in last.lower() or ":)" in last or "😀" in last
        )
        if high_energy and original_text:
            # Prepend a short upbeat cue only if it won't change meaning
            return [{"text": f"Opa! {original_text}", "delay_ms": 0}]
    except Exception:
        pass
    return [{"text": original_text, "delay_ms": 0}]
