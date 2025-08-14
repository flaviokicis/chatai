from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid hard import at runtime
    from .llm import LLMClient

# Human pacing defaults for multi-message outputs
MIN_FOLLOWUP_DELAY_MS = 2200
MAX_FOLLOWUP_DELAY_MS = 4000
MAX_MULTI_MESSAGES = 8

DEFAULT_INSTRUCTION = (
    "Reescreva o prompt em uma única pergunta amigável em português (Brasil), direcionada ao usuário. "
    "Requisitos: uma frase; sem listas ou marcadores; sem múltiplas alternativas; "
    "sem aspas; mantenha o significado; seja conciso."
)


def naturalize_prompt(llm: LLMClient, text: str, instruction: str | None = None) -> str:  # type: ignore[name-defined]
    instr = instruction or DEFAULT_INSTRUCTION
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


def clarify_and_reask(llm: LLMClient, question_text: str, user_message: str) -> str:  # type: ignore[name-defined]
    """Produce a brief acknowledgement that references the user's clarification,
    then restate the original question as a single sentence.
    """
    instr = (
        "O usuário pediu um esclarecimento sobre a pergunta. "
        "Escreva um breve reconhecimento que faça referência às palavras do usuário e depois reformule a pergunta de forma sucinta. "
        "Apenas uma frase; sem listas; sem aspas; mantenha o significado; seja conciso. Responda em português (Brasil)."
    )
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
        "Papel: você é uma recepcionista calorosa e amigável no WhatsApp.\n"
        "Tarefa: reescreva a resposta do assistente em mensagens curtas e naturais.\n"
        "Você decide quantas mensagens enviar (uma é ok; muitas vezes duas é ótimo).\n\n"
        "RESTRIÇÕES CRÍTICAS (obrigatórias):\n"
        "- Preserve o significado original EXATAMENTE. Não mude o tópico nem adicione detalhes.\n"
        "- Se o original incluir opções/entidades/unidades/números, reproduza-os AO PÉ DA LETRA (mesmas palavras, mesma ordem).\n"
        "- Não reescreva perguntas em outras palavras. Se o texto for uma pergunta, mantenha o texto EXATO da pergunta.\n"
        "- Apenas ajuste o tom e, se fizer sentido, divida em bolhas (sem gerar perguntas adicionais).\n\n"
        "- Não introduza palavras como 'revisitar' ou 'Vamos revisitar' a menos que já apareçam no texto original.\n\n"
        "Diretrizes de estilo:\n"
        "- Se o usuário acabou de responder ou corrigir algo, comece com um breve reconhecimento que faça referência a isso.\n"
        "- Mantenha amigável e sucinto; apenas texto simples.\n"
        "- Use transições mínimas apenas quando realmente ajudarem o fluxo; evite enfeites.\n"
        "- Mantenha cada mensagem com <= 120 caracteres.\n"
        "- Evite repetir saudações. Se a primeira mensagem for uma saudação (ex.: 'Oi!', 'Olá!'), a próxima NÃO deve começar com a mesma saudação.\n"
        "- Tempo: primeira mensagem delay_ms = 0; seguintes entre 2200-4000 ms.\n"
        "- Saída ESTRITAMENTE como um array JSON de {text: string, delay_ms: integer}.\n\n"
        "Se você não conseguir manter cada opção/entidade exatamente como escrito, retorne UMA única mensagem com o texto original e delay_ms = 0.\n\n"
        "Exemplos (apenas formato; o conteúdo deve manter o significado):\n"
        "Entrada: 'Poderia me dizer se é mais parecido com uma quadra de tênis ou um campo de futebol?'\n"
        '[\n  {"text": "Entendido!", "delay_ms": 0},\n  {"text": "É mais parecido com uma quadra de tênis ou um campo de futebol?", "delay_ms": 1600}\n]\n\n'
        "Entrada: 'É em ambiente interno (indoor) ou externo (outdoor)?'\n"
        '[\n  {"text": "É em ambiente interno (indoor) ou externo (outdoor)?", "delay_ms": 0}\n]\n\n'
        "Entrada: 'Com o que posso te ajudar hoje?'\n"
        '[\n  {"text": "Com o que posso te ajudar hoje?", "delay_ms": 0}\n]\n\n'
        "Importante: escreva as mensagens em português (Brasil)."
    )

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
        # Fall back to simple single-message naturalization
        pass

    # Fallback: single naturalized message
    try:
        first = naturalize_prompt(llm, original_text)
    except Exception:
        first = original_text
    return [{"text": first, "delay_ms": 0}]
