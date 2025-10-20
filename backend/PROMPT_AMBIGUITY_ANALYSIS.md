# LLM Prompt Ambiguity Analysis

## Problem Found in `services/responder.py` Lines 644-645

### Current (AMBIGUOUS) Triggers:

```python
**COMMUNICATION STYLE TRIGGERS:**
- "Mude a saudação para..." / "Altere o cumprimento..."
- "Termine as mensagens com..." / "Use essa despedida..."
```

## Why This Is Ambiguous

### Example 1: "Mude a saudação para..."

This phrase could mean TWO completely different things:

#### Flow Modification (Structural):
```
"Mude a saudação para perguntar o nome primeiro"
→ Should use: modify_flow
→ Changes: Flow graph structure (what question is asked)
```

#### Communication Style (Tone):
```
"Mude a saudação para ser mais calorosa"
→ Should use: update_communication_style
→ Changes: How greetings sound (tone)
```

**Current instructions would classify BOTH as communication style!** ❌

### Example 2: "Termine as mensagens com..."

#### Flow Modification (Structural):
```
"Termine as mensagens com uma pergunta de confirmação"
→ Should use: modify_flow
→ Changes: Adds a confirmation question node
```

#### Communication Style (Tone):
```
"Termine as mensagens com 'Qualquer dúvida, estou aqui!'"
→ Should use: update_communication_style
→ Changes: How messages end (closing style)
```

## Root Cause

The triggers don't check for **WHAT** is being changed:
- **Structure keywords** → Flow modification
- **Tone/style keywords** → Communication style

## More Ambiguous Examples

| User Request | Intended Meaning | Current Classification | Correct Classification |
|--------------|-----------------|----------------------|----------------------|
| "Mude a saudação para 'Qual seu nome?'" | Change greeting QUESTION | Communication Style ❌ | Flow Modification ✅ |
| "Mude a saudação para ser mais formal" | Change greeting TONE | Communication Style ✅ | Communication Style ✅ |
| "Altere o cumprimento para pedir email" | Add email to greeting | Communication Style ❌ | Flow Modification ✅ |
| "Altere o cumprimento para ser caloroso" | Change greeting tone | Communication Style ✅ | Communication Style ✅ |

## Recommended Fix

### Instead of listing ambiguous phrases, use SEMANTIC RULES:

```python
**HOW TO DISTINGUISH:**

Communication Style changes affect TONE/MANNER, not CONTENT:
- Formality level (formal, casual, professional)
- Emoji usage (more emojis, fewer emojis, no emojis)
- Message length (concise, detailed, brief)
- Personality traits (warm, direct, friendly, robotic)
- Word choice preferences (use X instead of Y)

Flow Modification changes affect STRUCTURE/CONTENT:
- What questions are asked
- Order of questions
- Adding/removing questions
- Splitting/merging question nodes
- Changing question prompts/text
- Routing logic

**KEY TEST:**
- If the request mentions WHAT to ask → Flow Modification
- If the request mentions HOW to talk → Communication Style
```

### Specific Pattern Analysis:

```python
"Mude a saudação para [X]" → Check X:
  - If X = question/pergunta/node content → Flow Modification
  - If X = tone/style/manner → Communication Style

"Seja mais [X]" → Always Communication Style
  - X = formal, direto, caloroso, educado, etc.

"Change this question to [X]" → Always Flow Modification
  - Explicitly mentions "question"

"Use [mais/menos] emojis" → Always Communication Style
  - About presentation, not content

"Add a question about [X]" → Always Flow Modification
  - Explicitly adding structure
```

## Test Cases

### Should be Communication Style:
```
✅ "Seja mais educado"
✅ "Use mais emojis"
✅ "Fale de forma mais direta"
✅ "Seja mais caloroso nas saudações"
✅ "Mude o tom para ser mais profissional"
✅ "Evite ser muito formal"
```

### Should be Flow Modification:
```
✅ "Mude a saudação para perguntar o nome"
✅ "Adicione uma pergunta sobre telefone"
✅ "Change this question to ask for email"
✅ "Divida esta pergunta em duas"
✅ "Remova a pergunta sobre endereço"
✅ "Altere a pergunta de CPF para RG"
```

### Currently Ambiguous (need better rules):
```
❓ "Mude a saudação para 'Olá! Qual seu nome?'"
   → Flow Modification (changing question text)
   → Currently: Might be classified as Communication Style

❓ "Termine as mensagens com uma pergunta"
   → Flow Modification (adding question node)
   → Currently: Classified as Communication Style

❓ "Altere o cumprimento inicial"
   → Depends on context! Need to look at what follows
   → Currently: Classified as Communication Style
```

## Proposed Solution

Replace the trigger lists with a decision tree:

```python
**DISTINGUISHING FLOW MODIFICATION vs COMMUNICATION STYLE:**

1. Check for EXPLICIT structure keywords:
   - "question" / "pergunta" / "prompt" / "nó" / "node"
   - "add" / "remove" / "adicionar" / "remover"
   - "split" / "divide" / "dividir" / "quebrar"
   - "merge" / "juntar" / "combinar"
   → If present → Flow Modification

2. Check for EXPLICIT style keywords:
   - "tom" / "tone" / "estilo" / "style"
   - "formal" / "informal" / "caloroso" / "direto"
   - "emoji" / "emoticon"
   - "mais/menos [adjective about manner]"
   - "como [pessoa/humano/amigo]"
   → If present → Communication Style

3. For ambiguous phrases ("mude a saudação para..."):
   - Look at what comes after
   - If it's a new question/text → Flow Modification
   - If it's a style adjective → Communication Style

4. Default heuristic:
   - If request changes WHAT is asked → Flow Modification
   - If request changes HOW it's said → Communication Style
```

## Impact Analysis

### Current Behavior (Wrong):
```
User: "Mude a saudação para perguntar o nome completo"

LLM sees: "Mude a saudação para..." → Communication Style trigger
LLM uses: update_communication_style
Result: Only updates tone, NOT the question ❌
```

### Expected Behavior (Correct):
```
User: "Mude a saudação para perguntar o nome completo"

LLM sees: "Mude a saudação para [perguntar...]" → Contains "perguntar" (structural)
LLM uses: modify_flow
Result: Changes the greeting question ✅
```

## Additional Ambiguous Patterns Found

Looking at the full trigger list:

### Line 644: "Mude a saudação para..."
- ❌ Can mean change question OR change tone
- Should check: What comes after?

### Line 645: "Termine as mensagens com..."
- ❌ Can mean add ending question OR change closing style
- Should check: Is it adding content or changing manner?

### Line 646: "Evite dizer..." / "Não mencione..."
- ✅ These are actually OK for communication style
- But could also mean "remove this question" (flow mod)
- Example ambiguity:
  - "Não mencione o preço" → Could mean remove price question (flow)
  - "Não mencione o preço" → Could mean avoid talking about price in responses (style)

### Line 647: "Troque a palavra X por Y"
- ✅ Generally OK for communication style
- But what if X and Y are different questions?
- "Troque 'CPF' por 'RG'" → Flow modification (change question)
- "Troque 'olá' por 'oi'" → Communication style (change greeting word)

## Severity Assessment

### High Severity (Definitely Wrong):
1. "Mude a saudação para..." → Can incorrectly trigger communication style for flow changes
2. "Termine as mensagens com..." → Can incorrectly trigger communication style for flow changes

### Medium Severity (Context-Dependent):
3. "Evite dizer..." → Needs context to determine
4. "Troque X por Y" → Needs to check if X/Y are structural or stylistic

## Recommended Actions

1. **Remove ambiguous triggers from hardcoded lists**
2. **Add semantic analysis instructions**
3. **Provide decision tree instead of keyword matching**
4. **Add examples showing the distinction**
5. **Test with ambiguous cases**

## Proposed New Instructions

See `PROMPT_FIX_PROPOSAL.md` for the complete rewrite.

