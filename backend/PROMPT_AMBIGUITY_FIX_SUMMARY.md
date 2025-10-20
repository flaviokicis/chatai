# Prompt Ambiguity Fix - Summary

## What Was Wrong

The LLM decision-maker (EnhancedFlowResponder) had **ambiguous trigger patterns** that could cause it to incorrectly classify admin requests.

### Problem Location
**File**: `backend/app/flow_core/services/responder.py`
**Lines**: 627-650 (old version)
**Function**: `_add_admin_instructions()`

### Specific Issues

#### Issue #1: "Mude a saudação para..."
Listed as a **Communication Style trigger**, but this phrase is AMBIGUOUS:

```python
# Could mean EITHER:
"Mude a saudação para perguntar o nome"  # Flow modification ✅
"Mude a saudação para ser mais calorosa"  # Communication style ✅

# But old prompt classified BOTH as communication style ❌
```

#### Issue #2: "Termine as mensagens com..."
Also listed as **Communication Style trigger**, but equally ambiguous:

```python
# Could mean EITHER:
"Termine as mensagens com uma pergunta de confirmação"  # Flow modification ✅
"Termine as mensagens com 'Abraço!'"  # Communication style ✅

# But old prompt classified BOTH as communication style ❌
```

### Impact

**Potential misclassifications:**
- "Mude a saudação para perguntar o CPF" → Would use `update_communication_style` ❌
  - Expected: `modify_flow` ✅
  - Result: Only tone changes, question stays the same

## What Was Fixed

### Old Approach (Keyword Lists)
```python
**FLOW MODIFICATION TRIGGERS:**
- "Change this question to..."
- "Add/remove a question..."
[...]

**COMMUNICATION STYLE TRIGGERS:**
- "Seja mais [formal/informal...]"
- "Mude a saudação para..."  ← AMBIGUOUS!
- "Termine as mensagens com..."  ← AMBIGUOUS!
[...]
```

### New Approach (Semantic Decision Logic)
```python
**CRITICAL: DISTINGUISHING modify_flow vs update_communication_style**

These are TWO COMPLETELY DIFFERENT actions:
1. modify_flow: Changes STRUCTURE (what questions)
2. update_communication_style: Changes TONE (how it talks)

**DECISION LOGIC:**

Use modify_flow when:
- Structural keywords: "pergunta", "question", "nó", "node"
- Action keywords: "adicionar", "add", "remover", "remove", "dividir", "split"
- Changes WHAT is asked

Use update_communication_style when:
- Style keywords: "tom", "tone", "estilo", "style"
- Personality keywords: "formal", "informal", "caloroso", "educado"
- Presentation keywords: "emoji", "emoticon", "conciso"
- Changes HOW it's said

For ambiguous phrases, analyze the OBJECT:
- "Mude a saudação para [perguntar X]" → modify_flow
- "Mude a saudação para [ser mais calorosa]" → update_communication_style

FUNDAMENTAL TEST:
- Changes WHAT content/questions? → modify_flow
- Changes HOW content is presented? → update_communication_style
```

## Key Improvements

### 1. Removed Ambiguous Triggers
❌ Removed: "Mude a saudação para..."
❌ Removed: "Termine as mensagens com..."
✅ Replaced with: Semantic analysis rules

### 2. Added Decision Logic
Instead of keyword matching, the LLM now:
1. Looks for structural keywords (pergunta, node, adicionar, etc.)
2. Looks for style keywords (tom, estilo, formal, emoji, etc.)
3. Analyzes the object of change for ambiguous phrases
4. Applies fundamental test: WHAT vs HOW

### 3. Added Explicit Examples
Shows both correct classifications with explanations:
```
✓ "Mude a saudação para PERGUNTAR o nome" (has "perguntar" → structural)
✓ "Mude o tom da saudação para SER MAIS CALOROSO" (has "tom" → style)
```

### 4. Added Ambiguity Resolution
Explicit rules for previously ambiguous cases:
```
"Mude a saudação para [perguntar X]" → modify_flow (changing question)
"Mude a saudação para [ser mais calorosa]" → update_communication_style (changing tone)
```

## Testing

### Test Cases That Would Have Failed Before

```python
# These would have been MISCLASSIFIED with old prompts:
misclassified_before = [
    ("Mude a saudação para perguntar o nome completo", "modify_flow"),
    # Old: Would match "Mude a saudação para..." → communication_style ❌
    # New: Sees "perguntar" → modify_flow ✅
    
    ("Termine as mensagens com uma pergunta de confirmação", "modify_flow"),
    # Old: Would match "Termine as mensagens com..." → communication_style ❌
    # New: Sees "pergunta" → modify_flow ✅
]

# These would have been CORRECTLY classified (no change):
correctly_classified_before = [
    ("Seja mais educado", "update_communication_style"),
    ("Use mais emojis", "update_communication_style"),
    ("Mude o tom para ser mais profissional", "update_communication_style"),
]
```

### Recommended Tests

```bash
# Test with admin CLI
cd backend
python admin_flow_cli.py --flow-file playground/flow_example.json

# Test cases:
Admin: "Mude a saudação para perguntar o email"
# Expected: modify_flow action

Admin: "Mude o tom da saudação para ser mais caloroso"
# Expected: update_communication_style action

Admin: "Seja mais educado"
# Expected: update_communication_style action

Admin: "Adicione uma pergunta sobre telefone"
# Expected: modify_flow action
```

## Files Changed

1. **`backend/app/flow_core/services/responder.py`**
   - Lines 627-678 updated
   - Function: `_add_admin_instructions()`
   - Change: Replaced keyword lists with semantic decision logic

## Files Created (Documentation)

1. **`PROMPT_AMBIGUITY_ANALYSIS.md`** - Detailed analysis of the problem
2. **`PROMPT_FIX_PROPOSAL.md`** - Proposed solution with examples
3. **`PROMPT_AMBIGUITY_FIX_SUMMARY.md`** - This file (summary)
4. **`ADMIN_COMMUNICATION_STYLE_PIPELINE.md`** - Communication style pipeline docs
5. **`ADMIN_SYSTEMS_COMPARISON.md`** - Side-by-side comparison
6. **`ADMIN_EDIT_FLOW_PIPELINE.md`** - Updated with clarifications
7. **`ADMIN_EDIT_FLOW_DIAGRAM.md`** - Updated with warnings

## Why This Matters

### Before Fix
```
Admin: "Mude a saudação para perguntar o CPF"

LLM: Sees "Mude a saudação para..." → Matches communication style trigger
LLM: Uses update_communication_style action
Database: Updates tenant.communication_style field
Result: Question stays the same, only tone might change ❌
```

### After Fix
```
Admin: "Mude a saudação para perguntar o CPF"

LLM: Analyzes request for structural keywords
LLM: Finds "perguntar" → Structural change
LLM: Uses modify_flow action
Database: Updates flows.definition with new question
Result: Question is actually changed ✅
```

## Backward Compatibility

This fix is **backward compatible** because:
1. Clear cases (with explicit keywords) work the same
2. Only ambiguous cases now have better classification
3. No breaking changes to the API or data structures
4. Just improved prompt instructions

## Monitoring

To verify the fix is working in production:

```python
# Log which action is chosen and why
logger.info(f"Admin request: {user_message}")
logger.info(f"Action chosen: {action_name}")
logger.info(f"Keywords found: {keywords}")
```

## Next Steps

1. ✅ Fix implemented in `services/responder.py`
2. ⏳ Test with ambiguous cases manually
3. ⏳ Monitor production logs for misclassifications
4. ⏳ Collect real-world edge cases
5. ⏳ Iterate if needed

## Summary

**Problem**: Keyword-based triggers caused ambiguous phrase misclassification
**Solution**: Semantic decision logic with structural/style keyword analysis
**Impact**: Better accuracy in distinguishing flow modifications from communication style changes
**Risk**: Low (backward compatible, only improves ambiguous cases)

