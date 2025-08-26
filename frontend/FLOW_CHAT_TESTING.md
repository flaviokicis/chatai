# Frontend Flow Chat Testing Guide

This document outlines manual testing procedures for the flow chat feature auto-refresh functionality.

## Overview

The flow chat feature now uses a robust structured response system that eliminates brittle pattern matching and provides reliable auto-refresh functionality.

## Key Components to Test

### 1. FlowEditorChat Component
- **Location**: `components/flow-viewer/FlowEditorChat.tsx`
- **Key Feature**: Auto-refresh based on `flow_was_modified` flag

### 2. Flow Detail Page  
- **Location**: `app/flows/[id]/page.tsx`
- **Key Feature**: React Query refetch on modification detection

## Manual Testing Checklist

### ✅ **Test 1: Successful Flow Modification**
```typescript
// User Action: Type "Mude a escala de 1 a 10 pra 1 a 5" and send
// Expected Behavior:

// 1. API Call
console.log("API Request sent to:", `/flows/${flowId}/chat/send`);

// 2. API Response Structure
console.log("API Response:", {
  messages: [/* chat messages */],
  flow_was_modified: true,        // ← KEY FLAG!
  modification_summary: "update_node: q.intensidade_dor - ..."
});

// 3. Frontend Detection (FlowEditorChat.tsx:155)
if (response.flow_was_modified) {
  console.log("✅ Flow modification confirmed by backend");
  toast.success("Fluxo modificado com sucesso");
  onFlowModified?.(); // ← Triggers auto-refresh
}

// 4. Parent Component Refresh (flows/[id]/page.tsx:28)
const handleFlowModified = async () => {
  console.log("🔄 Flow modification detected, refreshing...");
  await refetch(); // React Query refetch
  toast.success("Fluxo atualizado automaticamente!");
};

// Expected Results:
✅ Toast: "Fluxo modificado com sucesso"
✅ Loading overlay appears briefly
✅ Flow diagram updates with new scale (1-5)
✅ Toast: "Fluxo atualizado automaticamente!" 
✅ Console: "✅ Flow modification confirmed by backend"
✅ Console: "🔄 Flow modification detected, refreshing..."
```

### ✅ **Test 2: Information Query (No Modifications)**
```typescript
// User Action: Type "Como está o meu fluxo?" and send
// Expected Behavior:

// 1. API Response
console.log("API Response:", {
  messages: [/* informational response */],
  flow_was_modified: false,       // ← NO MODIFICATION
  modification_summary: null
});

// 2. Frontend Detection
if (response.flow_was_modified) {
  // This should NOT execute
} 

// Expected Results:
✅ Toast: "Fluxo modificado com sucesso" - NOT shown
✅ No auto-refresh triggered
✅ No loading overlay
✅ Only informational response displayed
```

### ✅ **Test 3: Multiple Modifications**
```typescript
// User Action: Complex request affecting multiple nodes
// Expected Behavior:

// API Response
console.log("API Response:", {
  messages: [/* multiple responses */],
  flow_was_modified: true,
  modification_summary: "update_node: q.test1 - ...; update_node: q.test2 - ..."
});

// Expected Results:
✅ Single auto-refresh after all changes
✅ Console shows detailed modification summary
✅ All changes visible in updated flow diagram
```

### ✅ **Test 4: Error Scenarios**
```typescript
// User Action: Invalid modification request
// Expected Behavior:

// API Response (error case)
console.log("API Response:", {
  messages: [/* error messages */],
  flow_was_modified: false,       // ← NO MODIFICATION ON ERROR
  modification_summary: null
});

// Expected Results:
✅ Error toast displayed
✅ No auto-refresh triggered
✅ Flow remains unchanged
✅ Retry functionality available
```

### ✅ **Test 5: Network Error Handling**
```typescript
// Simulate: Network request failure
// Expected Behavior:

try {
  const response = await api.flowChat.send(flowId, text);
  // ... success handling
} catch (err) {
  console.error("Failed to send message:", err);
  toast.error("Falha ao enviar mensagem");
  // Show retry UI
}

// Expected Results:
✅ Network error toast displayed
✅ No false modification flags
✅ Retry button available
✅ Error message in chat
```

## Browser DevTools Verification

### Network Tab
1. Open DevTools → Network
2. Send flow modification request
3. Check API response:
   ```json
   {
     "messages": [...],
     "flow_was_modified": true,
     "modification_summary": "..."
   }
   ```

### Console Logs
Look for these specific log messages:
```javascript
// Modification detection
"✅ Flow modification confirmed by backend"
"📝 Modifications: update_node: q.intensidade_dor - ..."

// Auto-refresh process
"🔄 Flow modification detected, refreshing..."
"✅ Flow refreshed successfully"
```

### React DevTools
1. Install React Developer Tools extension
2. Check component state updates:
   - `FlowEditorChat`: `messages` state updates
   - Flow detail page: `isRefreshing` state during refresh

## API Client Testing

### Type Safety Verification
```typescript
import { FlowChatResponse } from "@/lib/api-client";

// Verify TypeScript types
const response: FlowChatResponse = await api.flowChat.send(flowId, content);
console.log(response.flow_was_modified); // boolean
console.log(response.modification_summary); // string | undefined
```

### API Response Structure
```typescript
// Expected API response shape
interface FlowChatResponse {
  messages: FlowChatMessage[];
  flow_was_modified: boolean;
  modification_summary?: string;
}
```

## Performance Testing

### Auto-refresh Performance
```javascript
// Measure refresh time
console.time("auto-refresh");
await handleFlowModified();
console.timeEnd("auto-refresh");

// Expected: < 2 seconds for typical flow refresh
```

### Network Request Optimization
- Verify only necessary data is refetched
- Check React Query caching behavior
- Monitor request/response sizes

## Regression Testing

### Before/After Comparison
**Previous System (❌ Brittle)**:
- Pattern matching on 50+ Portuguese/English phrases
- False positives/negatives
- Maintenance nightmare

**Current System (✅ Robust)**:
- Single boolean flag from backend
- 100% reliable detection
- Zero maintenance overhead

### Critical Scenarios to Prevent Regression
1. **Pattern Matching Removal**: Verify no hardcoded success phrases
2. **Auto-refresh Reliability**: Must trigger on every successful modification
3. **Error Handling**: Must not trigger on failures
4. **Type Safety**: All API responses properly typed

## Test Results Documentation

### Test Execution Log
```markdown
Date: [DATE]
Tester: [NAME]
Browser: [BROWSER/VERSION]

## Test Results
- [ ] Test 1: Successful Flow Modification - PASS/FAIL
- [ ] Test 2: Information Query - PASS/FAIL  
- [ ] Test 3: Multiple Modifications - PASS/FAIL
- [ ] Test 4: Error Scenarios - PASS/FAIL
- [ ] Test 5: Network Errors - PASS/FAIL

## Issues Found
[List any issues discovered]

## Notes
[Additional observations]
```

## Future Automated Testing

When frontend testing framework is set up:

```typescript
// Jest/React Testing Library example
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FlowEditorChat } from './FlowEditorChat';

test('auto-refresh triggers on flow modification', async () => {
  const mockOnFlowModified = jest.fn();
  
  // Mock API response with modification
  mockApiResponse({
    messages: [/* ... */],
    flow_was_modified: true,
    modification_summary: "test modification"
  });
  
  render(<FlowEditorChat flowId="test" onFlowModified={mockOnFlowModified} />);
  
  // Send message
  await userEvent.type(screen.getByRole('textbox'), 'Test modification');
  await userEvent.click(screen.getByText('Enviar'));
  
  // Verify auto-refresh triggered
  await waitFor(() => {
    expect(mockOnFlowModified).toHaveBeenCalled();
  });
  
  // Verify success toast
  expect(screen.getByText('Fluxo modificado com sucesso')).toBeInTheDocument();
});
```

This testing strategy ensures the flow chat feature works reliably and prevents regressions to the previous brittle system.

