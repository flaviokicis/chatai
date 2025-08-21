"""Test path correction functionality in the flow engine."""

import pytest
from unittest.mock import Mock
from app.flow_core.llm_responder import LLMFlowResponder
from app.flow_core.state import FlowContext


class TestPathCorrection:
    """Test suite for path correction improvements."""

    def test_normalize_path_name_llm_match(self):
        """Test LLM-based path matching."""
        mock_llm = Mock()
        mock_llm.rewrite.return_value = "Option-A"
        
        responder = LLMFlowResponder(llm=mock_llm)
        ctx = FlowContext(flow_id="test")
        ctx.available_paths = ["Option-A", "Option-B", "Special/Path", "other"]
        
        # Test that LLM is called and result is validated
        result = responder._normalize_path_name("I want option A", ctx)
        assert result == "Option-A"
        mock_llm.rewrite.assert_called_once()
        
        # Verify the instruction contains available paths
        call_args = mock_llm.rewrite.call_args[0]
        instruction = call_args[0]
        assert "'Option-A'" in instruction
        assert "'Option-B'" in instruction

    def test_normalize_path_name_llm_none_response(self):
        """Test LLM returning 'none' for no match."""
        mock_llm = Mock()
        mock_llm.rewrite.return_value = "none"
        
        responder = LLMFlowResponder(llm=mock_llm)
        ctx = FlowContext(flow_id="test")
        ctx.available_paths = ["customer-support", "technical-issues", "billing/payments"]
        
        # Test that original input is returned when LLM says 'none'
        result = responder._normalize_path_name("something unrelated", ctx)
        assert result == "something unrelated"

    def test_normalize_path_name_llm_invalid_response(self):
        """Test handling of invalid LLM response."""
        mock_llm = Mock()
        mock_llm.rewrite.return_value = "invalid-path-not-in-list"
        
        responder = LLMFlowResponder(llm=mock_llm)
        ctx = FlowContext(flow_id="test")
        ctx.available_paths = ["valid-path-1", "valid-path-2"]
        
        # Test that original input is returned when LLM returns invalid path
        result = responder._normalize_path_name("user input", ctx)
        assert result == "user input"

    def test_normalize_path_name_llm_error(self):
        """Test handling of LLM errors."""
        mock_llm = Mock()
        mock_llm.rewrite.side_effect = Exception("LLM failed")
        
        responder = LLMFlowResponder(llm=mock_llm)
        ctx = FlowContext(flow_id="test")
        ctx.available_paths = ["path-1", "path-2"]
        
        # Test that original input is returned when LLM fails
        result = responder._normalize_path_name("user input", ctx)
        assert result == "user input"

    def test_normalize_path_name_no_paths_available(self):
        """Test behavior when no paths are available."""
        responder = LLMFlowResponder(llm=Mock())
        ctx = FlowContext(flow_id="test")
        ctx.available_paths = []
        
        # Test that original input is returned when no paths available
        result = responder._normalize_path_name("user input", ctx)
        assert result == "user input"
        
        # LLM should not be called
        responder._llm.rewrite.assert_not_called()

    def test_context_with_path_info(self):
        """Test that context includes path information."""
        responder = LLMFlowResponder(llm=None)
        ctx = FlowContext(flow_id="test")
        ctx.available_paths = ["path1", "path2", "path3"]
        ctx.active_path = "path1"
        ctx.answers = {"selected_path": "path1"}
        
        instruction = responder._build_instruction(
            prompt="Test question",
            pending_field="test_field",
            ctx=ctx,
            user_message="test message",
            allowed_values=None
        )
        
        # Check that path information is included
        assert "Available flow paths: path1, path2, path3" in instruction
        assert "Currently on path: path1" in instruction
        assert "Previously selected path: path1" in instruction

    def test_path_correction_tracking(self):
        """Test that path corrections are tracked."""
        ctx = FlowContext(flow_id="test")
        
        # Initial state
        assert ctx.path_corrections == 0
        
        # Simulate a path correction
        ctx.path_corrections += 1
        assert ctx.path_corrections == 1
        
        # Multiple corrections
        ctx.path_corrections += 1
        assert ctx.path_corrections == 2
