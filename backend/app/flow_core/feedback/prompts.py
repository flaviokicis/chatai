"""Feedback prompt builder for external action results.

This module builds prompts that inform the LLM about the actual results
of external actions, ensuring truthful responses.
"""

from __future__ import annotations

from ..actions import ActionResult


class FeedbackPromptBuilder:
    """Builds prompts for LLM feedback based on external action results."""

    def build_action_result_prompt(
        self, action_name: str, result: ActionResult, original_instruction: str | None = None
    ) -> str:
        """Build a prompt informing the LLM about an action result.

        Args:
            action_name: Name of the action that was executed
            result: Result of the action execution
            original_instruction: Original instruction from the LLM (if available)

        Returns:
            Formatted prompt for the LLM
        """
        lines = [
            "=== EXTERNAL ACTION EXECUTION RESULT ===",
            f"Action: {action_name}",
            f"Status: {'SUCCESS' if result.is_success else 'FAILED'}",
        ]

        if original_instruction:
            lines.extend(
                [
                    f"Original instruction: {original_instruction[:200]}{'...' if len(original_instruction) > 200 else ''}",
                ]
            )

        if result.is_success:
            lines.extend(
                [
                    f"Result: {result.message}",
                ]
            )
            if result.data:
                lines.append(f"Additional data: {result.data}")
        else:
            lines.extend(
                [
                    f"Error: {result.message}",
                ]
            )
            if result.error:
                lines.append(f"Technical details: {result.error}")

        lines.extend(
            [
                "",
                "IMPORTANT: You MUST acknowledge this actual result in your response.",
                "Do NOT assume success if the status shows FAILED.",
                "Do NOT make claims about actions that failed.",
                "Base your response on the ACTUAL result shown above.",
                "========================================",
            ]
        )

        return "\n".join(lines)

    def build_action_feedback_instruction(self, action_name: str, result: ActionResult) -> str:
        """Build instruction for how the LLM should handle the result.

        Args:
            action_name: Name of the action
            result: Action result

        Returns:
            Instruction text for the LLM
        """
        if result.is_success:
            if action_name == "modify_flow":
                return (
                    "The flow modification was successful. You should:\n"
                    "1. Confirm to the user that the changes were applied\n"
                    "2. Explain what was modified (if details are available)\n"
                    "3. Continue with the flow as normal\n"
                    "4. Be truthful about what actually happened"
                )
            return (
                f"The {action_name} action completed successfully. "
                "Acknowledge this success to the user and proceed accordingly."
            )
        
        # Handle modify_flow failures specially
        if action_name == "modify_flow":
            return (
                "The flow modification FAILED. You MUST:\n"
                "1. Apologize for the failure (e.g., 'Ops, deu erro ao modificar o fluxo')\n"
                "2. Explain what went wrong in simple terms:\n"
                "   - Use the error message provided above\n"
                "   - Translate technical errors into user-friendly language\n"
                "   - If it's a database error, mention it might be temporary\n"
                "   - If it's a configuration error, say it's an internal issue\n"
                "3. Tell the user NO changes were made to the flow\n"
                "4. Suggest they can try again or report the issue\n"
                "5. DO NOT claim the modification worked\n"
                "6. DO NOT ask follow-up questions about the modification - it failed\n\n"
                "Example response for database error:\n"
                "'Ops, deu erro ao tentar modificar o fluxo. Foi um problema ao acessar o banco de dados - "
                "pode ter sido instabilidade temporária. Nenhuma mudança foi feita. "
                "Quer tentar de novo ou prefere reportar esse erro?'\n\n"
                "Example response for flow not found:\n"
                "'Ops, o sistema não conseguiu encontrar o fluxo pra modificar. "
                "Pode ser um erro temporário no banco. Nenhuma alteração foi aplicada. "
                "Se continuar acontecendo, melhor reportar esse erro.'"
            )
        
        return (
            f"The {action_name} action FAILED. You MUST:\n"
            "1. Inform the user that the action failed\n"
            "2. Explain what went wrong (using the error message)\n"
            "3. Suggest alternative approaches if possible\n"
            "4. Do NOT pretend the action succeeded\n"
            "5. Do NOT make promises about changes that didn't happen"
        )
