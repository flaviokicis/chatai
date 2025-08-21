"""Prompt logging utility for debugging LLM interactions."""

import json
import os
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
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Log a prompt/response pair to a timestamped file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
        filename = f"{timestamp}_{prompt_type}_{model}.json"
        filepath = self.base_dir / filename
        
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "prompt_type": prompt_type,
            "model": model,
            "instruction": instruction,
            "input_text": input_text,
            "response": response,
            "metadata": metadata or {}
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # Don't fail the main process if logging fails
            print(f"Warning: Failed to log prompt to {filepath}: {e}")


# Global logger instance
prompt_logger = PromptLogger()
