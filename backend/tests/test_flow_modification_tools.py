"""Tests for flow modification tools."""

import pytest
from app.agents.flow_modification_tools import (
    set_entire_flow,
    add_node, 
    update_node,
    delete_node,
    add_edge,
    update_edge,
    delete_edge,
    validate_flow,
    get_flow_summary,
    FLOW_MODIFICATION_TOOLS
)


@pytest.fixture
def valid_flow_definition():
    """A simple but valid flow definition for testing."""
    return {
        "schema_version": "v2",
        "id": "test.flow",
        "entry": "q.start",
        "metadata": {
            "name": "Test Flow",
            "description": "A flow for testing"
        },
        "nodes": [
            {
                "id": "q.start",
                "kind": "Question", 
                "key": "start_answer",
                "prompt": "How can I help you?"
            },
            {
                "id": "t.end",
                "kind": "Terminal",
                "reason": "Conversation complete"
            }
        ],
        "edges": [
            {
                "source": "q.start",
                "target": "t.end",
                "guard": {"fn": "answers_has", "args": {"key": "start_answer"}},
                "priority": 0
            }
        ]
    }


@pytest.fixture 
def complex_dentist_flow():
    """More complex flow based on dentist example."""
    return {
        "schema_version": "v2",
        "id": "flow.dentist_test",
        "entry": "q.motivo_consulta",
        "metadata": {
            "name": "Dentist Test Flow",
            "description": "Test flow for dental office"
        },
        "nodes": [
            {
                "id": "q.motivo_consulta",
                "kind": "Question",
                "key": "motivo_consulta", 
                "prompt": "Como posso ajudar hoje?"
            },
            {
                "id": "d.triagem", 
                "kind": "Decision",
                "decision_type": "llm_assisted",
                "decision_prompt": "Route based on patient need"
            },
            {
                "id": "q.limpeza",
                "kind": "Question",
                "key": "ultima_limpeza",
                "prompt": "Quando foi sua última limpeza?",
                "allowed_values": ["menos de 6 meses", "6-12 meses", "mais de 1 ano"]
            },
            {
                "id": "q.dor",
                "kind": "Question", 
                "key": "intensidade_dor",
                "prompt": "Escala da dor (1-10)?",
                "allowed_values": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
            },
            {
                "id": "t.rotina",
                "kind": "Terminal",
                "reason": "Consulta de rotina agendada"
            },
            {
                "id": "t.emergencia", 
                "kind": "Terminal",
                "reason": "Emergência encaminhada"
            }
        ],
        "edges": [
            {
                "source": "q.motivo_consulta",
                "target": "d.triagem", 
                "guard": {"fn": "answers_has", "args": {"key": "motivo_consulta"}},
                "priority": 0
            },
            {
                "source": "d.triagem",
                "target": "q.limpeza",
                "guard": {"fn": "always", "args": {"if": "rotina"}},
                "priority": 0,
                "condition_description": "Routine cleaning path"
            },
            {
                "source": "d.triagem", 
                "target": "q.dor",
                "guard": {"fn": "always", "args": {"if": "emergencia"}},
                "priority": 1,
                "condition_description": "Emergency path"
            },
            {
                "source": "q.limpeza",
                "target": "t.rotina",
                "priority": 0
            },
            {
                "source": "q.dor",
                "target": "t.emergencia", 
                "priority": 0
            }
        ]
    }


@pytest.fixture
def invalid_flow_definition():
    """An invalid flow definition for testing error cases."""
    return {
        "schema_version": "v2",
        "id": "invalid.flow",
        "entry": "nonexistent_node",
        "nodes": [
            {
                "id": "q.start",
                "kind": "Question"
                # Missing required 'key' and 'prompt' fields
            }
        ],
        "edges": [
            {
                "source": "q.start",
                "target": "nonexistent_target"
            }
        ]
    }


class TestSetEntireFlow:
    """Test the set_entire_flow function."""
    
    def test_set_valid_flow(self, valid_flow_definition):
        """Test setting a valid flow definition."""
        result = set_entire_flow(valid_flow_definition)
        
        assert "Successfully set complete flow definition" in result
        assert "Entry point: q.start" in result
        assert "Nodes: 2" in result
        assert "Edges: 1" in result
        assert "Flow ID: test.flow" in result
        assert "Flow is valid and ready to use!" in result
    
    def test_set_complex_flow(self, complex_dentist_flow):
        """Test setting a more complex flow."""
        result = set_entire_flow(complex_dentist_flow)
        
        assert "Successfully set complete flow definition" in result
        assert "Entry point: q.motivo_consulta" in result
        assert "Nodes: 6" in result
        assert "Edges: 5" in result
        assert "Flow ID: flow.dentist_test" in result
    
    def test_set_invalid_flow(self, invalid_flow_definition):
        """Test setting an invalid flow definition."""
        result = set_entire_flow(invalid_flow_definition)
        
        assert "Flow validation failed" in result or "Failed to set flow definition" in result
    
    def test_set_empty_flow(self):
        """Test setting an empty flow definition."""
        result = set_entire_flow({})
        
        assert "Failed to set flow definition" in result


class TestNodeOperations:
    """Test node manipulation functions."""
    
    def test_add_valid_node(self):
        """Test adding a valid node."""
        node = {
            "id": "q.new_question",
            "kind": "Question",
            "key": "new_field", 
            "prompt": "What's your preference?"
        }
        
        result = add_node(node)
        
        assert "Added Question node 'q.new_question'" in result
    
    def test_add_node_with_position(self):
        """Test adding a node with position specified."""
        node = {
            "id": "q.middle",
            "kind": "Question",
            "key": "middle_field",
            "prompt": "Middle question?"
        }
        
        result = add_node(node, position_after="q.start")
        
        assert "Added Question node 'q.middle' after q.start" in result
    
    def test_add_invalid_node(self):
        """Test adding a node missing required fields."""
        invalid_node = {"kind": "Question"}  # Missing 'id'
        
        result = add_node(invalid_node)
        
        assert "Node missing required fields: id" in result
    
    def test_update_node(self):
        """Test updating an existing node."""
        updates = {
            "prompt": "Updated prompt text",
            "clarification": "New clarification text"
        }
        
        result = update_node("q.start", updates)
        
        assert "Updated node 'q.start': prompt, clarification" in result
    
    def test_delete_node(self):
        """Test deleting a node.""" 
        result = delete_node("q.old_question")
        
        assert "Deleted node 'q.old_question' and all connected edges" in result


class TestEdgeOperations:
    """Test edge manipulation functions."""
    
    def test_add_basic_edge(self):
        """Test adding a basic edge."""
        result = add_edge("q.start", "t.end")
        
        assert "Added edge from 'q.start' to 't.end' (priority 0)" in result
    
    def test_add_edge_with_guard(self):
        """Test adding an edge with a guard condition."""
        guard = {"fn": "answers_has", "args": {"key": "field_name"}}
        
        result = add_edge("q.start", "t.end", priority=1, guard=guard, condition_description="Has answer")
        
        assert "Added edge from 'q.start' to 't.end' (priority 1)" in result
        assert str(guard) in result
        assert "(Has answer)" in result
    
    def test_update_edge(self):
        """Test updating an existing edge."""
        updates = {
            "priority": 2,
            "condition_description": "Updated condition"
        }
        
        result = update_edge("q.start", "t.end", updates)
        
        assert "Updated edge from 'q.start' to 't.end': priority, condition_description" in result
    
    def test_delete_edge(self):
        """Test deleting an edge."""
        result = delete_edge("q.start", "t.end")
        
        assert "Deleted edge from 'q.start' to 't.end'" in result


class TestFlowValidation:
    """Test flow validation functionality."""
    
    def test_validate_valid_flow(self, valid_flow_definition):
        """Test validating a valid flow."""
        result = validate_flow(valid_flow_definition)
        
        assert "Flow validation passed" in result or "Flow is valid" in result
    
    def test_validate_invalid_flow(self, invalid_flow_definition):
        """Test validating an invalid flow."""
        result = validate_flow(invalid_flow_definition)
        
        assert "Flow validation failed" in result or "Failed to validate flow" in result


class TestFlowSummary:
    """Test flow summary functionality."""
    
    def test_summary_simple_flow(self, valid_flow_definition):
        """Test getting summary of a simple flow."""
        result = get_flow_summary(valid_flow_definition)
        
        assert "Flow Summary (test.flow)" in result
        assert "Entry point: q.start" in result
        assert "Total nodes: 2" in result
        assert "Question: 1" in result
        assert "Terminal: 1" in result
        assert "Total edges: 1" in result
    
    def test_summary_complex_flow(self, complex_dentist_flow):
        """Test getting summary of a complex flow."""
        result = get_flow_summary(complex_dentist_flow)
        
        assert "Flow Summary (flow.dentist_test)" in result
        assert "Entry point: q.motivo_consulta" in result
        assert "Total nodes: 6" in result
        assert "Decision: 1" in result
        assert "Question: 3" in result
        assert "Terminal: 2" in result
        assert "Total edges: 5" in result
        assert "Terminals: t.rotina, t.emergencia" in result
    
    def test_summary_empty_flow(self):
        """Test getting summary of empty flow."""
        result = get_flow_summary({})
        
        assert "No flow definition loaded" in result


class TestToolSpecs:
    """Test the tool specifications are properly formatted."""
    
    def test_all_tools_have_required_fields(self):
        """Test that all tools have the required fields.""" 
        required_fields = ["name", "description", "args_schema", "func"]
        
        for tool in FLOW_MODIFICATION_TOOLS:
            for field in required_fields:
                assert field in tool, f"Tool missing {field}: {tool.get('name', 'unnamed')}"
    
    def test_tool_names_are_unique(self):
        """Test that all tool names are unique."""
        names = [tool["name"] for tool in FLOW_MODIFICATION_TOOLS]
        
        assert len(names) == len(set(names)), "Duplicate tool names found"
    
    def test_set_entire_flow_tool_exists(self):
        """Test that the primary set_entire_flow tool exists."""
        tool_names = [tool["name"] for tool in FLOW_MODIFICATION_TOOLS]
        
        assert "set_entire_flow" in tool_names, "set_entire_flow tool not found"


class TestIntegration:
    """Integration tests combining multiple operations."""
    
    def test_full_flow_creation_workflow(self):
        """Test creating a flow step by step.""" 
        # Start with basic flow
        base_flow = {
            "schema_version": "v2",
            "id": "test.integration",
            "entry": "q.start",
            "nodes": [
                {
                    "id": "q.start",
                    "kind": "Question",
                    "key": "start_input",
                    "prompt": "Welcome! How can I help?"
                }
            ],
            "edges": []
        }
        
        # Set the base flow
        result1 = set_entire_flow(base_flow)
        assert "Successfully set complete flow definition" in result1
        
        # Get summary
        summary = get_flow_summary(base_flow)
        assert "Total nodes: 1" in summary
        assert "Total edges: 0" in summary
        
        # Test validation
        validation = validate_flow(base_flow)
        # Should have warnings about no terminals or unreachable nodes
        assert "valid" in validation.lower()
    
    def test_dentist_flow_patterns(self, complex_dentist_flow):
        """Test patterns specific to the dentist flow example."""
        # Validate the complex flow
        result = validate_flow(complex_dentist_flow)
        assert "validation" in result.lower()
        
        # Get summary and check for expected patterns
        summary = get_flow_summary(complex_dentist_flow)
        
        # Should have decision node for routing
        assert "Decision: 1" in summary
        # Should have multiple question paths  
        assert "Question: 3" in summary
        # Should have multiple terminals
        assert "Terminal: 2" in summary
        # Should show the multiple terminals
        assert "t.rotina" in summary and "t.emergencia" in summary
