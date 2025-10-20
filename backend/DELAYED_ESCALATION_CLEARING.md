# Delayed Context Clearing After Escalation

## Overview

This feature implements **delayed context clearing** after escalation to prevent user confusion when they send follow-up messages like "thank you" immediately after being escalated to a human agent.

## Problem

Previously, when a user was escalated to a human:
1. Chat history was cleared **immediately**
2. If user said "thank you" or similar, the bot had **no context**
3. User perceived this as a **system reset** - confusing experience

## Solution

Context is now cleared **after a configurable grace period** (default: 5 minutes):

```
User escalates → Context persists → User says "thanks" → Bot still has context
                    ↓
                After 5 minutes → Context cleared
```

## Implementation

### 1. **Configurable Delay Constant**

**File:** `backend/app/flow_core/constants.py`

```python
ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS = 300  # 5 minutes
```

### 2. **Redis Timestamp Tracking**

**File:** `backend/app/core/state.py`

New methods added to `RedisStore`:
- `set_escalation_timestamp()` - Mark when escalation occurred
- `get_escalation_timestamp()` - Retrieve escalation time
- `clear_escalation_timestamp()` - Remove escalation marker
- `should_clear_context_after_escalation()` - Check if grace period expired

**Redis Key Pattern:**
```
chatai:escalation:{user_id}:{agent_type}
```

**TTL:** 24 hours (auto-cleanup)

### 3. **Modified Escalation Flow**

**File:** `backend/app/agents/base.py`

**Before:**
```python
def _escalate(self, reason: str, summary: dict[str, Any]) -> AgentResult:
    # Clear immediately
    self.deps.store.clear_chat_history(self.user_id, self.agent_type)
    return AgentResult(...)
```

**After:**
```python
def _escalate(self, reason: str, summary: dict[str, Any]) -> AgentResult:
    # Mark escalation time
    self.deps.store.set_escalation_timestamp(self.user_id, self.agent_type)
    
    # Schedule background task to clear after delay
    asyncio.create_task(
        self._clear_context_after_delay(
            self.user_id, 
            self.agent_type, 
            ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS
        )
    )
    
    return AgentResult(...)
```

### 4. **Dual Clearing Mechanism**

The implementation uses **two clearing mechanisms** for robustness:

#### A. Background Task (Primary)
```python
async def _clear_context_after_delay(
    self, user_id: str, agent_type: str, delay_seconds: int
) -> None:
    await asyncio.sleep(delay_seconds)
    # Clear context after delay
    self.deps.store.clear_chat_history(user_id, agent_type)
    self.deps.store.clear_escalation_timestamp(user_id, agent_type)
```

#### B. On-Message Check (Fallback)
```python
def handle(self, message: InboundMessage) -> AgentResult:
    # Check if grace period expired on each message
    if self.deps.store.should_clear_context_after_escalation(
        self.user_id, self.agent_type, ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS
    ):
        # Clear if grace period has passed
        self.deps.store.clear_chat_history(self.user_id, self.agent_type)
        self.deps.store.clear_escalation_timestamp(self.user_id, self.agent_type)
    
    # Continue normal processing...
```

**Why both mechanisms?**
- **Background task**: Clears context exactly after 5 minutes (efficient)
- **On-message check**: Ensures clearing happens even if server restarts (robust)

## User Experience

### Scenario 1: User Says "Thank You"
```
15:00:00 User: "I need help with billing"
15:00:05 Bot: "Transferindo você para um atendente humano..."
15:00:10 User: "Obrigado!"
15:00:11 Bot: [Still has context, can respond naturally]
15:05:05 [Context cleared automatically]
```

### Scenario 2: Grace Period Expires
```
15:00:00 User escalates
15:00:05 Bot escalates user
15:05:05 [5 minutes pass - context cleared]
15:06:00 User: "Hello again"
15:06:01 Bot: [Fresh conversation, no context from before]
```

## Configuration

To change the grace period, modify the constant in `constants.py`:

```python
ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS = 300  # Change to desired seconds
```

**Recommended values:**
- **300 seconds (5 minutes)** - Default, balances UX and privacy
- **180 seconds (3 minutes)** - Shorter grace period
- **600 seconds (10 minutes)** - Longer grace period for complex handoffs

## Testing

**Test File:** `backend/tests/unit/test_delayed_escalation_clearing.py`

**Tests:**
1. ✅ Escalation timestamp is set correctly
2. ✅ Context NOT cleared immediately after escalation
3. ✅ Grace period check works correctly
4. ✅ Background task clears context after delay
5. ✅ No escalation means no clearing
6. ✅ Constant is set to 300 seconds
7. ✅ Escalation timestamp can be cleared

**Run tests:**
```bash
cd backend
source .venv/bin/activate
pytest tests/unit/test_delayed_escalation_clearing.py -v
```

**Expected output:**
```
7 passed, 2 warnings in 0.15s
```

## Redis Keys

All escalation timestamps are stored in Redis with the pattern:

```
chatai:escalation:{user_id}:{agent_type}
```

**Example:**
```
Key: chatai:escalation:whatsapp:+5511999998888:flow
Value: 1729468800.123456 (Unix timestamp)
TTL: 86400 seconds (24 hours)
```

## Logging

The system logs all escalation clearing events:

```python
# On escalation
logger.info(
    "Escalation marked for user %s. Context will be cleared after %ds grace period.",
    user_id,
    ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS,
)

# After grace period (background task)
logger.info(
    "Cleared %d chat history keys for user %s after %ds grace period",
    deleted_keys,
    user_id,
    delay_seconds,
)

# After grace period (on-message check)
logger.info(
    "Cleared %d chat history keys for user %s (grace period expired)",
    deleted_keys,
    user_id,
)
```

## Benefits

✅ **Better UX** - Users can say "thanks" without bot appearing reset  
✅ **Configurable** - Single constant controls grace period  
✅ **Robust** - Dual clearing mechanism (background + on-message)  
✅ **Privacy** - Context still cleared automatically  
✅ **Tested** - 7 comprehensive tests ensure correctness  
✅ **Production-ready** - Type-safe, logged, idempotent  

## Files Modified

1. `backend/app/flow_core/constants.py` - Added constant
2. `backend/app/core/state.py` - Added timestamp tracking methods
3. `backend/app/agents/base.py` - Modified escalation flow
4. `backend/tests/unit/test_delayed_escalation_clearing.py` - Tests

## Migration Notes

**No migration needed** - Backward compatible:
- Existing systems without Redis methods will skip timestamp tracking
- `hasattr()` checks ensure graceful degradation
- Works with both RedisStore and InMemoryStore (InMemoryStore won't track, just clears immediately as before)

## Future Enhancements

Potential improvements:
1. Make grace period **per-tenant configurable** (not just constant)
2. Add **admin API** to manually clear context before grace period
3. **Metrics/analytics** on grace period usage
4. Different grace periods for **different escalation reasons**

