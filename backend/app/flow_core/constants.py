"""Constants for the flow core system.

This module defines all constants used throughout the flow processing system,
avoiding magic numbers and providing clear, maintainable configuration.
"""

# Message generation constants
MIN_FOLLOWUP_DELAY_MS = 2200
MAX_FOLLOWUP_DELAY_MS = 4000
DEFAULT_DELAY_MS = 2500
NO_DELAY_MS = 0
MAX_DELAY_ALLOWED_MS = 5000

# Message content limits
MAX_MESSAGE_LENGTH = 150
MESSAGE_TRUNCATION_LENGTH = 147
TRUNCATION_SUFFIX = "..."
MAX_MESSAGES_PER_TURN = 3
MIN_MESSAGES_PER_TURN = 1
MAX_MESSAGES_ALLOWED = 5

# Text field limits
MAX_ACKNOWLEDGMENT_LENGTH = 140
MAX_REASONING_LENGTH = 500
MAX_CONTEXT_SUMMARY_LENGTH = 500
MAX_TOOL_NAME_LENGTH = 50

# Retry and validation
MAX_SCHEMA_VALIDATION_RETRIES = 2
MAX_VALIDATION_ERRORS_TO_SHOW = 3

# Confidence thresholds
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0
DEFAULT_CONFIDENCE = 1.0
LOW_CONFIDENCE_THRESHOLD = 0.5
HIGH_CONFIDENCE_THRESHOLD = 0.8

# List limits
MAX_NEXT_STEPS = 5
MIN_DICT_ITEMS = 1
MAX_HISTORY_TURNS = 150
MAX_RECENT_HISTORY = 5

# Conversation tracking
DEFAULT_CLARIFICATION_COUNT = 0
MAX_CLARIFICATION_ATTEMPTS = 3
DEFAULT_PATH_CORRECTIONS = 0
DEFAULT_TURN_COUNT = 0

# Urgency levels
URGENCY_LOW = "low"
URGENCY_MEDIUM = "medium"
URGENCY_HIGH = "high"
DEFAULT_URGENCY = URGENCY_MEDIUM

# Completion types
COMPLETION_SUCCESS = "success"
COMPLETION_PARTIAL = "partial"
COMPLETION_ABANDONED = "abandoned"
DEFAULT_COMPLETION_TYPE = COMPLETION_SUCCESS

# Navigation types
NAV_TYPE_NEXT = "next"
NAV_TYPE_SKIP = "skip"
NAV_TYPE_BACK = "back"
NAV_TYPE_JUMP = "jump"
DEFAULT_NAV_TYPE = NAV_TYPE_JUMP

# Clarification reasons
CLARIFICATION_UNCLEAR = "unclear_response"
CLARIFICATION_OFF_TOPIC = "off_topic"
CLARIFICATION_NEEDS_EXPLANATION = "needs_explanation"
CLARIFICATION_FORMAT = "format_clarification"

# Handoff reasons
HANDOFF_FRUSTRATED = "user_frustrated"
HANDOFF_EXPLICIT = "explicit_request"
HANDOFF_TOO_COMPLEX = "too_complex"
HANDOFF_TECHNICAL = "technical_issue"

# Tool names (for type safety)
TOOL_PERFORM_ACTION = "PerformAction"

# Model names
MODEL_GPT5 = "gpt-5"
MODEL_GPT4 = "gpt-4"
MODEL_GEMINI_FLASH = "gemini-2.5-flash-lite"

# Prompt types for logging
PROMPT_TYPE_GPT5_ENHANCED = "gpt5_enhanced"
PROMPT_TYPE_TOOL_CALLING = "tool_calling"
PROMPT_TYPE_TOOL_ERROR = "tool_calling_error"
PROMPT_TYPE_NATURALIZATION = "whatsapp_naturalization"

# Role types
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"

# Default messages
DEFAULT_ERROR_MESSAGE = "Desculpe, tive um problema. Pode repetir sua mensagem?"
DEFAULT_HELP_MESSAGE = "Entendi. Vou te ajudar com isso."
DEFAULT_ACKNOWLEDGMENT = "Ok, entendi."

# Metadata keys
META_ERROR = "error"
META_REASONING = "reasoning"
META_VALIDATED = "validated"
META_TOOL_NAME = "tool_name"
META_NAV_TYPE = "navigation_type"
META_RESTART = "restart"
META_MESSAGE_COUNT = "message_count"
META_ATTEMPT = "attempt"
META_NEEDS_VALIDATION = "needs_validation"

# Validation settings
REQUIRED_UPDATE_FIELDS = 1
MAX_UPDATE_FIELDS = 10

# Character limits for user input
MAX_USER_MESSAGE_LENGTH = 1000
MAX_PROMPT_LENGTH = 5000

# Default values
DEFAULT_FLOW_ID = "unknown"
DEFAULT_SESSION_ID = "unknown"
DEFAULT_USER_ID = "unknown"
DEFAULT_AGENT_TYPE = "flow_responder"

# Brazilian Portuguese common expressions
BR_CONTRACTIONS = ["tá", "pra", "né"]
BR_GREETINGS = ["olá", "oi", "boa tarde", "bom dia", "boa noite"]

# Timeout values (in milliseconds)
THOUGHT_TRACE_TIMEOUT_MS = 30000
TOOL_EXECUTION_TIMEOUT_MS = 10000

# Escalation settings
ESCALATION_CONTEXT_CLEAR_DELAY_SECONDS = 300

# Cache settings
MAX_CONTEXT_CACHE_SIZE = 100
CONTEXT_CACHE_TTL_SECONDS = 3600
