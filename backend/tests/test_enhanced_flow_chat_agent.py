"""Tests for the enhanced FlowChatAgent with prompt and tools."""

import json
from unittest.mock import Mock, MagicMock
import pytest

from app.agents.flow_chat_agent import FlowChatAgent, ToolSpec
from app.agents.flow_modification_tools import FLOW_MODIFICATION_TOOLS
from app.core.llm import LLMClient


@pytest.fixture
def mock_llm():
    """Mock LLM client for testing."""
    llm = Mock(spec=LLMClient)
    return llm


@pytest.fixture
def flow_tools():
    """Convert flow modification tools to ToolSpec format."""
    tools = []
    for tool_config in FLOW_MODIFICATION_TOOLS:
        tools.append(ToolSpec(
            name=tool_config["name"],
            description=tool_config["description"],
            args_schema=tool_config["args_schema"],
            func=tool_config["func"]
        ))
    return tools


@pytest.fixture
def agent_with_tools(mock_llm, flow_tools):
    """FlowChatAgent configured with modification tools."""
    return FlowChatAgent(llm=mock_llm, tools=flow_tools)


@pytest.fixture
def sample_flow():
    """Sample flow for testing."""
    return {
        "schema_version": "v2",
        "id": "test.sample",
        "entry": "q.start",
        "metadata": {"name": "Sample Flow"},
        "nodes": [
            {"id": "q.start", "kind": "Question", "key": "start", "prompt": "How can I help?"},
            {"id": "t.end", "kind": "Terminal", "reason": "Done"}
        ],
        "edges": [
            {"source": "q.start", "target": "t.end", "priority": 0}
        ]
    }


class TestFlowChatAgentPrompt:
    """Test the enhanced prompt building in FlowChatAgent."""
    
    def test_prompt_contains_role_description(self, agent_with_tools, sample_flow):
        """Test that prompt contains proper role description."""
        history = []
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        assert "expert flow editing assistant" in prompt
        assert "conversational flows" in prompt
        assert "JSON-based flow language" in prompt
    
    def test_prompt_contains_capabilities(self, agent_with_tools, sample_flow):
        """Test that prompt lists key capabilities."""
        history = []
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        # Check for key capabilities
        assert "Create complete flows from scratch" in prompt
        assert "Modify existing flows" in prompt
        assert "Create subgraphs" in prompt
        assert "Add decision logic" in prompt
    
    def test_prompt_contains_flow_language_docs(self, agent_with_tools, sample_flow):
        """Test that prompt includes flow language documentation."""
        history = []
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        # Check for node type documentation
        assert "Question" in prompt and "asks user for information" in prompt.lower()
        assert "Decision" in prompt and "routes conversation" in prompt.lower()
        assert "Terminal" in prompt and "ends the conversation" in prompt.lower()
        
        # Check for edge documentation
        assert "source" in prompt and "target" in prompt
        assert "priority" in prompt and "lower numbers evaluated first" in prompt
    
    def test_prompt_contains_subgraph_explanation(self, agent_with_tools, sample_flow):
        """Test that prompt explains subgraphs."""
        history = []
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        assert "Subgraphs" in prompt
        assert "specialized conversation paths" in prompt
        assert "When to Use Subgraphs" in prompt
        assert "Different product/service categories" in prompt
        assert "Emergency vs. routine cases" in prompt
    
    def test_prompt_contains_dentist_example(self, agent_with_tools, sample_flow):
        """Test that prompt includes the dentist flow example."""
        history = []
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        assert "Dentist Office Flow" in prompt
        assert "consultorio_dentista" in prompt
        assert "motivo_consulta" in prompt
        assert "triagem_inicial" in prompt
        
        # Check for key pattern explanations
        assert "Entry Point" in prompt
        assert "Main Decision" in prompt
        assert "Subgraphs" in prompt
        assert "Convergence" in prompt
        assert "Smart Terminals" in prompt
    
    def test_prompt_contains_whatsapp_instructions(self, agent_with_tools, sample_flow):
        """Test that prompt has WhatsApp conversation handling instructions."""
        history = []
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        assert "WhatsApp Conversation" in prompt
        assert "Analyze the conversation flow" in prompt
        assert "Extract key questions" in prompt
        assert "Identify decision points" in prompt
        assert "Create appropriate subgraphs" in prompt
    
    def test_prompt_shows_current_flow(self, agent_with_tools, sample_flow):
        """Test that prompt displays the current flow."""
        history = []
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        assert "Current Flow:" in prompt
        assert "test.sample" in prompt  # Flow ID should be visible
        assert "q.start" in prompt      # Node should be visible
    
    def test_prompt_shows_conversation_history(self, agent_with_tools, sample_flow):
        """Test that prompt includes conversation history."""
        history = [
            {"role": "user", "content": "I want to create a new flow"},
            {"role": "assistant", "content": "I'll help you create that flow"}
        ]
        prompt = agent_with_tools._build_prompt(sample_flow, history)
        
        assert "Conversation History:" in prompt
        assert "User: I want to create a new flow" in prompt
        assert "Assistant: I'll help you create that flow" in prompt
    
    def test_prompt_handles_empty_flow(self, agent_with_tools):
        """Test that prompt handles empty flow gracefully."""
        history = []
        prompt = agent_with_tools._build_prompt({}, history)
        
        assert "Current Flow:" in prompt
        assert "null" in prompt or "{}" in prompt
    
    def test_dentist_example_structure(self, agent_with_tools):
        """Test that the embedded dentist example has correct structure."""
        history = []
        prompt = agent_with_tools._build_prompt({}, history)
        
        # Extract the dentist example from the prompt
        dentist_example = agent_with_tools._get_dentist_flow_example()
        
        # Verify key structural elements
        assert dentist_example["id"] == "flow.consultorio_dentista"
        assert dentist_example["entry"] == "q.motivo_consulta"
        assert "nodes" in dentist_example
        assert "edges" in dentist_example
        
        # Verify it has the main decision node
        decision_nodes = [n for n in dentist_example["nodes"] if n.get("kind") == "Decision"]
        assert len(decision_nodes) >= 1
        assert any("triagem" in n.get("id", "") for n in decision_nodes)
        
        # Verify it has multiple question paths
        question_nodes = [n for n in dentist_example["nodes"] if n.get("kind") == "Question"]
        assert len(question_nodes) >= 3  # Should have multiple questions for different paths
        
        # Verify it has multiple terminals
        terminal_nodes = [n for n in dentist_example["nodes"] if n.get("kind") == "Terminal"]
        assert len(terminal_nodes) >= 2  # Different outcomes


class TestFlowChatAgentTools:
    """Test the tool integration in FlowChatAgent."""
    
    def test_agent_has_modification_tools(self, agent_with_tools):
        """Test that agent is configured with flow modification tools."""
        tool_names = list(agent_with_tools.tools.keys())
        
        # Check for key tools
        assert "set_entire_flow" in tool_names
        assert "add_node" in tool_names
        assert "add_edge" in tool_names
        assert "validate_flow" in tool_names
        assert "get_flow_summary" in tool_names
    
    def test_tool_execution_set_entire_flow(self, agent_with_tools, sample_flow, mock_llm):
        """Test that set_entire_flow tool can be executed."""
        # Mock LLM to return a tool call
        mock_llm.extract.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "name": "set_entire_flow",
                    "arguments": {"flow_definition": sample_flow}
                }
            ]
        }
        
        history = [{"role": "user", "content": "Set this flow"}]
        outputs = agent_with_tools.process(sample_flow, history)
        
        assert len(outputs) > 0
        assert "Successfully set complete flow definition" in outputs[0]
    
    def test_tool_execution_get_flow_summary(self, agent_with_tools, sample_flow, mock_llm):
        """Test that get_flow_summary tool can be executed."""
        mock_llm.extract.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "name": "get_flow_summary", 
                    "arguments": {"flow_definition": sample_flow}
                }
            ]
        }
        
        history = [{"role": "user", "content": "Show me a summary"}]
        outputs = agent_with_tools.process(sample_flow, history)
        
        assert len(outputs) > 0
        assert "Flow Summary (test.sample)" in outputs[0]
    
    def test_tool_execution_add_node(self, agent_with_tools, sample_flow, mock_llm):
        """Test that add_node tool can be executed."""
        new_node = {
            "id": "q.middle",
            "kind": "Question",
            "key": "middle_answer", 
            "prompt": "What's next?"
        }
        
        mock_llm.extract.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "name": "add_node",
                    "arguments": {"node_definition": new_node}
                }
            ]
        }
        
        history = [{"role": "user", "content": "Add a new question"}]
        outputs = agent_with_tools.process(sample_flow, history)
        
        assert len(outputs) > 0
        assert "Added Question node 'q.middle'" in outputs[0]
    
    def test_multiple_tool_calls(self, agent_with_tools, sample_flow, mock_llm):
        """Test that agent can handle multiple tool calls."""
        call_count = 0
        
        def mock_extract_side_effect(prompt, tool_schemas):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                return {
                    "content": "Let me analyze this flow first",
                    "tool_calls": [
                        {
                            "name": "get_flow_summary",
                            "arguments": {"flow_definition": sample_flow}
                        }
                    ]
                }
            else:
                return {"content": None, "tool_calls": []}
        
        mock_llm.extract.side_effect = mock_extract_side_effect
        
        history = [{"role": "user", "content": "Analyze this flow"}]
        outputs = agent_with_tools.process(sample_flow, history)
        
        # Should have both the content message and the tool output
        assert len(outputs) >= 2
        assert "Let me analyze this flow first" in outputs[0]
        assert "Flow Summary (test.sample)" in outputs[1]
    
    def test_invalid_tool_call_handling(self, agent_with_tools, sample_flow, mock_llm):
        """Test that agent handles invalid tool calls gracefully."""
        call_count = 0
        
        def mock_extract_side_effect(prompt, tool_schemas):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                return {
                    "content": "I'll help with that",
                    "tool_calls": [
                        {
                            "name": "nonexistent_tool", 
                            "arguments": {"some": "args"}
                        }
                    ]
                }
            else:
                return {"content": None, "tool_calls": []}
        
        mock_llm.extract.side_effect = mock_extract_side_effect
        
        history = [{"role": "user", "content": "Do something"}]
        outputs = agent_with_tools.process(sample_flow, history)
        
        # Should return the content but skip the invalid tool
        assert len(outputs) == 1
        assert "I'll help with that" in outputs[0]
    
    def test_loop_prevention(self, agent_with_tools, sample_flow, mock_llm):
        """Test that agent prevents infinite loops."""
        # Mock LLM to always return tool calls
        mock_llm.extract.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "name": "get_flow_summary",
                    "arguments": {"flow_definition": sample_flow}
                }
            ]
        }
        
        history = [{"role": "user", "content": "Keep going"}]
        outputs = agent_with_tools.process(sample_flow, history)
        
        # Should be limited to reasonable number (hard limit is 10 iterations)
        assert len(outputs) <= 10


class TestFlowChatAgentIntegration:
    """Integration tests for the complete agent functionality."""
    
    def test_complete_flow_creation_scenario(self, agent_with_tools, mock_llm):
        """Test a complete flow creation scenario."""
        # Simulate user asking to create a complete flow
        mock_llm.extract.return_value = {
            "content": "I'll create a complete flow for you",
            "tool_calls": [
                {
                    "name": "set_entire_flow",
                    "arguments": {
                        "flow_definition": {
                            "schema_version": "v2",
                            "id": "new.flow",
                            "entry": "q.welcome",
                            "nodes": [
                                {"id": "q.welcome", "kind": "Question", "key": "name", "prompt": "What's your name?"},
                                {"id": "t.done", "kind": "Terminal", "reason": "Complete"}
                            ],
                            "edges": [
                                {"source": "q.welcome", "target": "t.done", "priority": 0}
                            ]
                        }
                    }
                }
            ]
        }
        
        history = [{"role": "user", "content": "Create a simple welcome flow"}]
        outputs = agent_with_tools.process({}, history)
        
        assert len(outputs) >= 2
        assert "I'll create a complete flow for you" in outputs[0]
        assert "Successfully set complete flow definition" in outputs[1]
        assert "new.flow" in outputs[1]
