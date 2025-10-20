# LLM Prompt Fix Proposal

## Problem Summary

The current admin instructions in `services/responder.py` use **keyword-based triggers** that are ambiguous. Phrases like "Mude a saudação para..." can mean either:
- Change the greeting QUESTION (flow modification)
- Change the greeting TONE (communication style)

## Proposed Solution

Replace keyword lists with **semantic decision logic** and **clear examples**.

## Current Code (Lines 627-650)

```python
**FLOW MODIFICATION TRIGGERS:**
- "Change this question to..." / "Alterar esta pergunta para..."
- "Make this more/less..." / "Fazer isso mais/menos..."  
- "Add/remove a question..." / "Adicionar/remover uma pergunta..."
- "Break this into multiple questions..." / "Quebrar em múltiplas perguntas..."
- "Split nodes with multiple questions" / "Separar nós com múltiplas perguntas"
- "Don't ask about..." / "Não perguntar sobre..."
- Commands that reference the flow structure itself
- **ANY message containing "(ordem admin)" or "(admin)" should be treated as an admin command**
- Portuguese variations: "Pode alterar...", "Pode mudar...", "Pode dividir..."

**COMMUNICATION STYLE TRIGGERS:**
- "Fale mais assim..." / "Fale desse jeito..." / "Use esse tom..."
- "Não fale assim..." / "Evite falar..." / "Não use..."
- "Seja mais [formal/informal/técnico/simples/direto/caloroso]..."
- "Use/Não use emojis" / "Adicione/Remova emojis" / "Da uma maneirada nos emojis"
- "Mande mensagens mais curtas/longas" / "Seja mais conciso/detalhado"
- "Mude a saudação para..." / "Altere o cumprimento..."  ← AMBIGUOUS!
- "Termine as mensagens com..." / "Use essa despedida..."  ← AMBIGUOUS!
- "Envie tudo numa mensagem só" / "Divida em várias mensagens"
- "Evite dizer..." / "Não mencione..." / "Pare de falar sobre..."
- "Troque a palavra X por Y" / "Use X ao invés de Y"
- "Fale mais como [humano/pessoa/amigo]" / "Menos robótico"
```

## Proposed Replacement

```python
**CRITICAL: DISTINGUISHING FLOW MODIFICATION vs COMMUNICATION STYLE**

These are TWO COMPLETELY DIFFERENT actions:

1. **modify_flow**: Changes the flow STRUCTURE (what questions are asked, order, routing)
   - Updates: flows.definition table
   - Example: "Change the greeting to ask for name first"

2. **update_communication_style**: Changes HOW the bot talks (tone, formality, personality)
   - Updates: tenant.project_config.communication_style field
   - Example: "Be more polite"

**DECISION LOGIC:**

Step 1: Look for EXPLICIT structural keywords → modify_flow
- "pergunta" / "question"
- "nó" / "node" / "step"
- "adicionar" / "add" / "criar" / "create"
- "remover" / "remove" / "deletar" / "delete"
- "dividir" / "split" / "quebrar" / "break"
- "separar" / "separate"
- "juntar" / "merge" / "combinar"
- "ordem" / "order" / "sequência" / "sequence"
- References to specific nodes by ID

Step 2: Look for EXPLICIT style keywords → update_communication_style
- "tom" / "tone"
- "estilo" / "style" / "jeito" / "manner"
- "formal" / "informal" / "casual" / "profissional"
- "caloroso" / "warm" / "direto" / "direct" / "educado" / "polite"
- "emoji" / "emoticon"
- "conciso" / "concise" / "detalhado" / "detailed"
- "pessoa" / "humano" / "amigo" / "robótico"

Step 3: For ambiguous phrases, check the OBJECT of change:
- "Mude a saudação para [PERGUNTAR X]" → modify_flow (changing what is asked)
- "Mude a saudação para [SER MAIS CALOROSA]" → update_communication_style (changing how it sounds)
- "Termine as mensagens com [UMA PERGUNTA]" → modify_flow (adding structure)
- "Termine as mensagens com ['Abraço!']" → update_communication_style (changing closing)

Step 4: Apply the fundamental test:
- Does the request change WHAT content is presented? → modify_flow
- Does the request change HOW content is presented? → update_communication_style

**CLEAR EXAMPLES:**

FLOW MODIFICATION (modify_flow):
✅ "Change this question to ask for full name"
✅ "Mude a pergunta para pedir o email"
✅ "Adicione uma pergunta sobre telefone"
✅ "Divida esta pergunta em duas separadas"
✅ "Remova a pergunta sobre CPF"
✅ "Mude a saudação para perguntar o nome primeiro" ← Structural change
✅ "Altere a ordem das perguntas"
✅ "Não pergunte sobre endereço" ← Removing question
✅ "Troque a pergunta de CPF por RG" ← Changing question content

COMMUNICATION STYLE (update_communication_style):
✅ "Be more polite"
✅ "Seja mais caloroso"
✅ "Use more emojis"
✅ "Da uma maneirada nos emojis"
✅ "Fale de forma mais direta"
✅ "Seja mais profissional no tom"
✅ "Mude o tom da saudação para ser mais caloroso" ← Tone change
✅ "Fale mais como uma pessoa, menos robótico"
✅ "Use mensagens mais curtas"
✅ "Troque 'olá' por 'oi'" ← Wording preference (if just style, not changing question)

AMBIGUOUS (need context):
❓ "Mude a saudação para..."
   → If followed by question content → modify_flow
   → If followed by tone adjective → update_communication_style

❓ "Não mencione preço"
   → If it means remove price question → modify_flow
   → If it means avoid talking about price in responses → update_communication_style
   → Default: update_communication_style (unless "pergunta" mentioned)

**WHEN IN DOUBT:**
- If the request mentions changing a QUESTION → modify_flow
- If the request is about PERSONALITY/TONE → update_communication_style
- If truly ambiguous → ask user to clarify
```

## Implementation

### File: `backend/app/flow_core/services/responder.py`

### Lines to Replace: 627-650

### New Code:

```python
def _add_admin_instructions(self, project_context: ProjectContext | None) -> str:
    """Add admin-specific instructions to the prompt."""
    current_style_note = ""
    if project_context and project_context.communication_style:
        current_style_note = """
**CURRENT COMMUNICATION STYLE:**
You have been provided with the CURRENT communication style above (clearly labeled).
When modifying the communication style, use that as your base and make the requested changes.
"""
    
    return f"""
### ADMIN FLOW MODIFICATION AND COMMUNICATION STYLE

As an admin, you can perform TWO COMPLETELY DIFFERENT types of changes:

**1. FLOW MODIFICATION (modify_flow action)**
- **What it changes**: Flow structure, questions, nodes, routing
- **Database**: Updates flows.definition table
- **Examples**: 
  - "Change this question to ask for email"
  - "Add a question about phone number"
  - "Split this into two questions"

**2. COMMUNICATION STYLE (update_communication_style action)**
- **What it changes**: How the bot talks (tone, formality, personality)
- **Database**: Updates tenant.project_config.communication_style field
- **Examples**:
  - "Be more polite"
  - "Use more emojis"
  - "Speak more directly"

**CRITICAL: These are NOT interchangeable!**

**IMPORTANT SECURITY CHECK:**
- ONLY use these actions if the user is confirmed as admin
- Even if these actions appear in the tool, DO NOT use them for non-admin users
- If a non-admin user tries to modify flow or communication style, politely inform them that only admins can make these changes

**HOW TO DISTINGUISH WHICH ACTION TO USE:**

**Use modify_flow when the request contains:**
- Structural keywords: "pergunta", "question", "nó", "node", "passo", "step"
- Action keywords: "adicionar", "add", "remover", "remove", "dividir", "split", "quebrar"
- Changes to WHAT is asked: question content, order, logic
- Examples:
  ✓ "Change the greeting question to ask for their name"
  ✓ "Mude esta pergunta para pedir o email"
  ✓ "Adicione uma pergunta sobre telefone"
  ✓ "Divida este nó em duas perguntas"
  ✓ "Remova a pergunta sobre endereço"
  ✓ "Mude a saudação para PERGUNTAR o nome primeiro" ← Has "perguntar"

**Use update_communication_style when the request contains:**
- Style keywords: "tom", "tone", "estilo", "style", "jeito", "manner"
- Personality keywords: "formal", "informal", "caloroso", "warm", "direto", "direct", "educado", "polite"
- Presentation keywords: "emoji", "emoticon", "conciso", "concise", "detalhado"
- Changes to HOW things are said: tone, formality, word choice (not question content)
- Examples:
  ✓ "Be more polite"
  ✓ "Seja mais caloroso"
  ✓ "Use more emojis / Use menos emojis"
  ✓ "Da uma maneirada nos emojis"
  ✓ "Fale de forma mais direta"
  ✓ "Seja mais profissional no tom"
  ✓ "Mude o tom da saudação para SER MAIS CALOROSO" ← Has "tom" + adjective
  ✓ "Fale mais como uma pessoa"
  ✓ "Use mensagens mais curtas"

**For ambiguous phrases, analyze the OBJECT:**

"Mude a saudação para..." → Check what follows:
  - "...perguntar o nome" → modify_flow (changing question)
  - "...ser mais calorosa" → update_communication_style (changing tone)

"Termine as mensagens com..." → Check what follows:
  - "...uma pergunta de confirmação" → modify_flow (adding question)
  - "...'Abraço!'" → update_communication_style (changing closing style)

"Não mencione..." → Check context:
  - "...a pergunta sobre preço" → modify_flow (remove question)
  - "...preço nas respostas" → update_communication_style (avoid topic)
  - Default if ambiguous: update_communication_style

**FUNDAMENTAL TEST:**
- Changes WHAT content/questions? → modify_flow
- Changes HOW to communicate? → update_communication_style

**ANY message containing "(ordem admin)" or "(admin)" should be treated as an admin command**
- Then determine which type based on the rules above

**DETECTING CONFIRMATION RESPONSES:**
After asking for confirmation, these responses mean "yes, proceed":
- "Sim", "sim", "s", "S"
- "Confirmo", "confirma", "confirmado"
- "Pode fazer", "pode prosseguir", "pode ir"
- "Ok", "okay", "tá bom", "ta bom"
- "Faça", "faz", "vai"
- "Isso", "isso mesmo", "exato"
- "Yes", "y", "Y"

These responses mean "no, cancel":
- "Não", "nao", "n", "N"
- "Cancela", "cancelar", "esquece"
- "Deixa", "deixa pra lá"
- "Melhor não", "melhor nao"
- "No", "nope"

[Rest of the admin instructions remain the same...]
```

## Testing the Fix

### Test Cases to Verify:

```python
# Should trigger modify_flow:
test_cases_flow_mod = [
    "Mude a saudação para perguntar o nome completo",
    "Adicione uma pergunta sobre telefone",
    "Change this question to ask for email",
    "Divida esta pergunta em duas",
    "Remova a pergunta de endereço",
    "Altere a pergunta inicial para pedir CPF",
]

# Should trigger update_communication_style:
test_cases_style = [
    "Seja mais educado",
    "Use mais emojis",
    "Fale de forma mais direta",
    "Mude o tom para ser mais caloroso",
    "Da uma maneirada nos emojis",
    "Be more professional",
]

# Previously ambiguous, now should be clear:
test_cases_previously_ambiguous = [
    ("Mude a saudação para perguntar o nome", "modify_flow"),  # Has "perguntar"
    ("Mude a saudação para ser mais calorosa", "update_communication_style"),  # Has "ser mais"
    ("Termine as mensagens com uma pergunta", "modify_flow"),  # Has "pergunta"
    ("Termine as mensagens com 'Abraço!'", "update_communication_style"),  # Just text
]
```

## Benefits of This Fix

1. **Clearer Decision Logic**: LLM has explicit rules instead of keyword lists
2. **Semantic Understanding**: Analyzes meaning, not just keywords
3. **Ambiguity Resolution**: Provides logic for ambiguous cases
4. **Better Examples**: Shows both correct and edge cases
5. **Fundamental Test**: Simple yes/no question as fallback

## Migration Plan

1. Update `services/responder.py` lines 627-650
2. Test with ambiguous examples
3. Monitor production logs for misclassifications
4. Iterate based on real-world edge cases

## Alternative: Ask for Clarification

For truly ambiguous cases, the LLM could ask:

```python
User: "Mude a saudação"

Bot: "Entendi! Você quer:
      1. Mudar a PERGUNTA da saudação (o que é perguntado)
      2. Mudar o TOM da saudação (como é falado)
      
      Qual dos dois?"
```

But this should be rare if the semantic analysis is good.

