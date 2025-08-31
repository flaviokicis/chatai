"""Unit tests for flow modification tools with mocked dependencies."""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.agents.flow_modification_tools import (
    set_entire_flow,
    update_edge,
    update_node,
)


@pytest.fixture
def mock_session():
    """Mock SQLAlchemy session."""
    session = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    session.flush = Mock()
    return session


@pytest.fixture
def mock_flow_id():
    """Mock flow ID."""
    return uuid4()


@pytest.fixture
def sample_flow_definition():
    """Sample flow definition for testing."""
    return {
        "schema_version": "v1",
        "id": "test.flow",
        "entry": "q.start",
        "nodes": [
            {
                "id": "q.intensidade_dor",
                "key": "intensidade_dor",
                "kind": "Question",
                "prompt": "Em uma escala de 1 a 10, qual a intensidade da sua dor?",
                "allowed_values": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
            },
            {
                "id": "d.nivel_emergencia",
                "kind": "Decision",
                "label": "Classificação do nível de emergência",
                "decision_type": "llm_assisted",
                "decision_prompt": "Com base na intensidade da dor, determinar se é emergência imediata (dor 8-10), urgente (dor 5-7), ou pode aguardar agendamento (dor 1-4)"
            }
        ],
        "edges": [
            {
                "source": "d.nivel_emergencia",
                "target": "q.disponibilidade_hoje",
                "priority": 0,
                "guard": {"fn": "always", "args": {"if": "dor 8-10, emergência imediata"}},
                "condition_description": "Subcaminho: emergência imediata"
            }
        ]
    }


class TestUpdateNode:
    """Tests for update_node function."""

    @patch("app.agents.flow_modification_tools.set_entire_flow")
    def test_update_node_success(self, mock_set_entire_flow, sample_flow_definition, mock_flow_id, mock_session):
        """Test successful node update."""
        # Arrange
        mock_set_entire_flow.return_value = "✅ Fluxo atualizado com sucesso!"
        updates = {
            "prompt": "Em uma escala de 1 a 5, qual a intensidade da sua dor?",
            "allowed_values": ["1", "2", "3", "4", "5"]
        }

        # Act
        result = update_node(
            flow_definition=sample_flow_definition,
            node_id="q.intensidade_dor",
            updates=updates,
            user_message="Escala atualizada com sucesso!",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Assert
        assert "Escala atualizada com sucesso!" in result
        # Verify the node was updated in memory
        updated_node = next(node for node in sample_flow_definition["nodes"] if node["id"] == "q.intensidade_dor")
        assert updated_node["prompt"] == "Em uma escala de 1 a 5, qual a intensidade da sua dor?"
        assert updated_node["allowed_values"] == ["1", "2", "3", "4", "5"]
        # Verify set_entire_flow was called
        mock_set_entire_flow.assert_called_once()

    def test_update_node_not_found(self, sample_flow_definition):
        """Test updating non-existent node."""
        # Act
        result = update_node(
            flow_definition=sample_flow_definition,
            node_id="q.nonexistent",
            updates={"prompt": "test"},
            user_message="Should fail"
        )

        # Assert
        assert "Node 'q.nonexistent' not found" in result

    def test_update_node_no_updates(self, sample_flow_definition):
        """Test update with empty updates."""
        # Act
        result = update_node(
            flow_definition=sample_flow_definition,
            node_id="q.intensidade_dor",
            updates={},
            user_message="Empty updates"
        )

        # Assert
        assert "No updates provided" in result


class TestUpdateEdge:
    """Tests for update_edge function."""

    @patch("app.agents.flow_modification_tools.set_entire_flow")
    def test_update_edge_success(self, mock_set_entire_flow, sample_flow_definition, mock_flow_id, mock_session):
        """Test successful edge update."""
        # Arrange
        mock_set_entire_flow.return_value = "✅ Fluxo atualizado com sucesso!"
        updates = {
            "guard": {"fn": "always", "args": {"if": "dor 5, emergência imediata"}},
            "condition_description": "Subcaminho: emergência imediata (dor 5)"
        }

        # Act
        result = update_edge(
            flow_definition=sample_flow_definition,
            source="d.nivel_emergencia",
            target="q.disponibilidade_hoje",
            updates=updates,
            user_message="Condição atualizada!",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Assert
        assert "Condição atualizada!" in result
        # Verify edge was updated
        updated_edge = next(edge for edge in sample_flow_definition["edges"]
                          if edge["source"] == "d.nivel_emergencia" and edge["target"] == "q.disponibilidade_hoje")
        assert updated_edge["guard"]["args"]["if"] == "dor 5, emergência imediata"
        assert updated_edge["condition_description"] == "Subcaminho: emergência imediata (dor 5)"
        mock_set_entire_flow.assert_called_once()

    def test_update_edge_not_found(self, sample_flow_definition):
        """Test updating non-existent edge."""
        # Act
        result = update_edge(
            flow_definition=sample_flow_definition,
            source="nonexistent",
            target="also_nonexistent",
            updates={"priority": 1},
            user_message="Should fail"
        )

        # Assert
        assert "Edge from 'nonexistent' to 'also_nonexistent' not found" in result


class TestSetEntireFlow:
    """Tests for set_entire_flow function."""

    @patch("app.agents.flow_modification_tools.repository.update_flow_with_versioning")
    @patch("app.agents.flow_modification_tools.FlowCompiler")
    @patch("app.agents.flow_modification_tools.FlowIR")
    def test_set_entire_flow_success(self, mock_flow_ir, mock_compiler, mock_update_flow,
                                   sample_flow_definition, mock_flow_id, mock_session):
        """Test successful flow update."""
        # Arrange
        mock_flow_ir.model_validate.return_value = Mock()
        mock_compiler_instance = Mock()
        mock_compiler.return_value = mock_compiler_instance
        mock_compiled = Mock()
        mock_compiled.validation_errors = []
        mock_compiled.errors = []  # Fix: Also mock the errors attribute
        mock_compiler_instance.compile.return_value = mock_compiled

        mock_updated_flow = Mock()
        mock_updated_flow.version = 42
        mock_update_flow.return_value = mock_updated_flow

        # Act
        result = set_entire_flow(
            flow_definition=sample_flow_definition,
            user_message="Fluxo atualizado!",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Assert
        assert "Fluxo atualizado!" in result  # This is the user_message we passed in
        mock_update_flow.assert_called_once_with(
            mock_session,
            flow_id=mock_flow_id,
            new_definition=sample_flow_definition,
            change_description="Complete flow replacement with 2 nodes",
            created_by="flow_chat_agent"
        )


class TestPainScaleUpdateScenario:
    """Integration-style test for the pain scale update scenario we've been debugging."""

    @patch("app.agents.flow_modification_tools.set_entire_flow")
    def test_pain_scale_update_1_to_5(self, mock_set_entire_flow, sample_flow_definition, mock_flow_id, mock_session):
        """Test the exact pain scale update scenario: 1-10 to 1-5."""
        # Arrange
        mock_set_entire_flow.return_value = "✅ Fluxo atualizado com sucesso!"

        # Act 1: Update the pain intensity question
        result1 = update_node(
            flow_definition=sample_flow_definition,
            node_id="q.intensidade_dor",
            updates={
                "prompt": "Em uma escala de 1 a 5, qual a intensidade da sua dor?",
                "allowed_values": ["1", "2", "3", "4", "5"]
            },
            user_message="Escala de dor alterada de 1-10 para 1-5 com sucesso!",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Act 2: Update the emergency classification decision
        result2 = update_node(
            flow_definition=sample_flow_definition,
            node_id="d.nivel_emergencia",
            updates={
                "decision_prompt": "Com base na intensidade da dor (1-5), determinar se é emergência imediata (5), urgente (3-4), ou pode aguardar (1-2)"
            },
            user_message="Regras de classificação de emergência atualizadas para a nova escala (5: imediata; 3-4: urgente; 1-2: pode aguardar).",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Act 3: Update emergency routing condition
        result3 = update_edge(
            flow_definition=sample_flow_definition,
            source="d.nivel_emergencia",
            target="q.disponibilidade_hoje",
            updates={
                "guard": {"fn": "always", "args": {"if": "dor 5, emergência imediata"}},
                "condition_description": "Subcaminho: emergência imediata (dor 5)"
            },
            user_message="Condição de emergência imediata ajustada para dor 5.",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Assert all operations succeeded
        assert "Escala de dor alterada de 1-10 para 1-5 com sucesso!" in result1
        assert "Regras de classificação de emergência atualizadas" in result2
        assert "Condição de emergência imediata ajustada para dor 5" in result3

        # Verify the actual changes were made to the flow definition
        pain_node = next(node for node in sample_flow_definition["nodes"] if node["id"] == "q.intensidade_dor")
        decision_node = next(node for node in sample_flow_definition["nodes"] if node["id"] == "d.nivel_emergencia")
        emergency_edge = next(edge for edge in sample_flow_definition["edges"]
                            if edge["source"] == "d.nivel_emergencia" and edge["target"] == "q.disponibilidade_hoje")

        # Critical assertions - these are the exact changes we expect
        assert pain_node["allowed_values"] == ["1", "2", "3", "4", "5"]
        assert "1 a 5" in pain_node["prompt"]
        assert "(1-5)" in decision_node["decision_prompt"]
        assert "emergência imediata (5)" in decision_node["decision_prompt"]
        assert "urgente (3-4)" in decision_node["decision_prompt"]
        assert "aguardar (1-2)" in decision_node["decision_prompt"]
        assert "dor 5" in emergency_edge["guard"]["args"]["if"]

        # Verify set_entire_flow was called for each update
        assert mock_set_entire_flow.call_count == 3

    @patch("app.agents.flow_modification_tools.set_entire_flow")
    def test_pain_scale_update_with_persistence_failure(self, mock_set_entire_flow, sample_flow_definition, mock_flow_id, mock_session):
        """Test what happens when persistence fails during pain scale update."""
        # Arrange - First call succeeds, second fails
        mock_set_entire_flow.side_effect = [
            "✅ Fluxo atualizado com sucesso!",  # First call succeeds
            "Failed to set flow definition: Database connection lost"  # Second call fails
        ]

        # Act 1: Update the pain scale (should succeed)
        result1 = update_node(
            flow_definition=sample_flow_definition,
            node_id="q.intensidade_dor",
            updates={
                "prompt": "Em uma escala de 1 a 5, qual a intensidade da sua dor?",
                "allowed_values": ["1", "2", "3", "4", "5"]
            },
            user_message="Should succeed",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Act 2: Update decision logic (should fail)
        result2 = update_node(
            flow_definition=sample_flow_definition,
            node_id="d.nivel_emergencia",
            updates={
                "decision_prompt": "Updated prompt"
            },
            user_message="Should fail",
            flow_id=mock_flow_id,
            session=mock_session
        )

        # Assert
        assert "Should succeed" in result1
        assert "Failed to set flow definition" in result2
        assert "Database connection lost" in result2
