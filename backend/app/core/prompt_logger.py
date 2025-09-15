"""Prompt logging utility for debugging LLM interactions."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class PromptLogger:
    """Logger for LLM prompts and responses."""

    def __init__(self, base_dir: str = "/tmp/chatai-prompts"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def log_prompt(
        self,
        prompt_type: str,
        instruction: str,
        input_text: str,
        response: str,
        model: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a prompt/response pair to both JSON and readable TXT files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds

        # Save JSON file (structured data)
        json_filename = f"{timestamp}_{prompt_type}_{model}.json"
        json_filepath = self.base_dir / json_filename

        log_data = {
            "timestamp": datetime.now().isoformat(),
            "prompt_type": prompt_type,
            "model": model,
            "instruction": instruction,
            "input_text": input_text,
            "response": response,
            "metadata": metadata or {},
        }

        # Save TXT file (readable format)
        txt_filename = f"{timestamp}_{prompt_type}_{model}.txt"
        txt_filepath = self.base_dir / txt_filename

        readable_content = f"""=== {prompt_type.upper()} PROMPT LOG ===
Timestamp: {datetime.now().isoformat()}
Model: {model}
Metadata: {json.dumps(metadata or {}, indent=2, ensure_ascii=False)}

=== INSTRUCTION ===
{instruction}

=== INPUT ===
{input_text}

=== RESPONSE ===
{response}

=== END LOG ===
"""

        try:
            # Save JSON
            with open(json_filepath, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            # Save readable TXT
            with open(txt_filepath, "w", encoding="utf-8") as f:
                f.write(readable_content)

        except Exception as e:
            # Don't fail the main process if logging fails
            print(f"Warning: Failed to log prompt to {json_filepath}/{txt_filepath}: {e}")


# Global logger instance
prompt_logger = PromptLogger()
