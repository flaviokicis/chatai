"""
Unit tests for flow path finding functionality.

These tests ensure that _find_decision_node_for_path correctly identifies
the right decision node for specific paths, preventing navigation bugs
where users get stuck in wrong flow branches.
"""

import pytest

from app.flow_core.compiler import FlowCompiler
from app.flow_core.engine import LLMFlowEngine
from app.flow_core.ir import DecisionNode, Edge, Flow, GuardRef, QuestionNode, TerminalNode
from app.flow_core.state import FlowContext


class MockLLM:
    """Mock LLM for testing purposes."""


class TestFlowPathFinding:
    """Test cases for decision node path finding."""

    def create_multi_decision_flow(self) -> Flow:
        """Create a flow with multiple decision nodes to test path finding."""
        return Flow(
            id="test_multi_decision",
            entry="q.start",
            nodes=[
                # Initial question
                QuestionNode(
                    id="q.start",
                    kind="Question",
                    key="start_question",
                    prompt="What do you need?"
                ),

                # Main routing decision
                DecisionNode(
                    id="d.main_routing",
                    kind="Decision",
                    label="Main routing decision",
                    decision_type="llm_assisted"
                ),

                # Sports sub-decision
                DecisionNode(
                    id="d.sports_type",
                    kind="Decision",
                    label="Sports type decision",
                    decision_type="llm_assisted"
                ),

                # Questions for different paths
                QuestionNode(id="q.lighting_specs", kind="Question", key="lighting_specs", prompt="Lighting specs?"),
                QuestionNode(id="q.sports_info", kind="Question", key="sports_info", prompt="Sports info?"),
                QuestionNode(id="q.tennis_details", kind="Question", key="tennis_details", prompt="Tennis details?"),
                QuestionNode(id="q.football_details", kind="Question", key="football_details", prompt="Football details?"),
                QuestionNode(id="q.industrial_specs", kind="Question", key="industrial_specs", prompt="Industrial specs?"),

                # Terminals
                TerminalNode(id="t.lighting_end", kind="Terminal", reason="Lighting handled"),
                TerminalNode(id="t.sports_end", kind="Terminal", reason="Sports handled"),
                TerminalNode(id="t.industrial_end", kind="Terminal", reason="Industrial handled"),
            ],
            edges=[
                # Flow progression
                Edge(source="q.start", target="d.main_routing", guard=GuardRef(fn="always"), priority=0),

                # Main routing paths
                Edge(
                    source="d.main_routing",
                    target="q.lighting_specs",
                    guard=GuardRef(fn="always"),
                    priority=0,
                    condition_description="Lighting Solutions"
                ),
                Edge(
                    source="d.main_routing",
                    target="d.sports_type",
                    guard=GuardRef(fn="always"),
                    priority=1,
                    condition_description="Sports Facilities"
                ),
                Edge(
                    source="d.main_routing",
                    target="q.industrial_specs",
                    guard=GuardRef(fn="always"),
                    priority=2,
                    condition_description="Industrial Solutions"
                ),

                # Sports sub-routing paths
                Edge(
                    source="d.sports_type",
                    target="q.tennis_details",
                    guard=GuardRef(fn="always"),
                    priority=0,
                    condition_description="Tennis Courts"
                ),
                Edge(
                    source="d.sports_type",
                    target="q.football_details",
                    guard=GuardRef(fn="always"),
                    priority=1,
                    condition_description="Football Fields"
                ),

                # Endings
                Edge(source="q.lighting_specs", target="t.lighting_end", guard=GuardRef(fn="always"), priority=0),
                Edge(source="q.tennis_details", target="t.sports_end", guard=GuardRef(fn="always"), priority=0),
                Edge(source="q.football_details", target="t.sports_end", guard=GuardRef(fn="always"), priority=0),
                Edge(source="q.industrial_specs", target="t.industrial_end", guard=GuardRef(fn="always"), priority=0),
            ]
        )

    def create_luminárias_flow(self) -> Flow:
        """Create a simplified version of the actual luminárias flow for testing."""
        return Flow(
            id="test_luminarias",
            entry="q.interesse_inicial",
            nodes=[
                QuestionNode(
                    id="q.interesse_inicial",
                    kind="Question",
                    key="interesse_inicial",
                    prompt="Qual é o seu interesse?"
                ),
                DecisionNode(
                    id="d.roteamento_principal",
                    kind="Decision",
                    label="Roteamento principal",
                    decision_type="llm_assisted"
                ),
                DecisionNode(
                    id="d.cobertura_quadra",
                    kind="Decision",
                    label="Tipo de cobertura",
                    decision_type="llm_assisted"
                ),
                QuestionNode(id="q.dados_posto", kind="Question", key="dados_posto", prompt="Dados do posto?"),
                QuestionNode(id="q.dados_ginasio", kind="Question", key="dados_ginasio", prompt="Dados do ginásio?"),
                QuestionNode(id="q.dimensoes_coberta", kind="Question", key="dimensoes_coberta", prompt="Dimensões cobertas?"),
                QuestionNode(id="q.dimensoes_descoberta", kind="Question", key="dimensoes_descoberta", prompt="Dimensões descobertas?"),
                TerminalNode(id="t.posto_end", kind="Terminal", reason="Posto handled"),
                TerminalNode(id="t.quadra_end", kind="Terminal", reason="Quadra handled"),
            ],
            edges=[
                Edge(source="q.interesse_inicial", target="d.roteamento_principal", guard=GuardRef(fn="always"), priority=0),

                # Main routing
                Edge(
                    source="d.roteamento_principal",
                    target="q.dados_posto",
                    guard=GuardRef(fn="always"),
                    priority=0,
                    condition_description="Posto de gasolina"
                ),
                Edge(
                    source="d.roteamento_principal",
                    target="q.dados_ginasio",
                    guard=GuardRef(fn="always"),
                    priority=1,
                    condition_description="Ginásio/Quadra"
                ),

                # Quadra sub-routing
                Edge(source="q.dados_ginasio", target="d.cobertura_quadra", guard=GuardRef(fn="always"), priority=0),
                Edge(
                    source="d.cobertura_quadra",
                    target="q.dimensoes_coberta",
                    guard=GuardRef(fn="always"),
                    priority=0,
                    condition_description="Quadra coberta"
                ),
                Edge(
                    source="d.cobertura_quadra",
                    target="q.dimensoes_descoberta",
                    guard=GuardRef(fn="always"),
                    priority=1,
                    condition_description="Quadra descoberta"
                ),

                # Endings
                Edge(source="q.dados_posto", target="t.posto_end", guard=GuardRef(fn="always"), priority=0),
                Edge(source="q.dimensoes_coberta", target="t.quadra_end", guard=GuardRef(fn="always"), priority=0),
                Edge(source="q.dimensoes_descoberta", target="t.quadra_end", guard=GuardRef(fn="always"), priority=0),
            ]
        )

    def setup_engine(self, flow: Flow) -> LLMFlowEngine:
        """Compile flow and create engine for testing."""
        compiler = FlowCompiler()
        compiled = compiler.compile(flow)
        return LLMFlowEngine(compiled, MockLLM())

    def test_find_correct_decision_node_for_specific_path(self):
        """Test that the function finds the correct decision node for a specific path."""
        flow = self.create_multi_decision_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Test main routing paths
        assert engine._find_decision_node_for_path(ctx, "Lighting Solutions") == "d.main_routing"
        assert engine._find_decision_node_for_path(ctx, "Sports Facilities") == "d.main_routing"
        assert engine._find_decision_node_for_path(ctx, "Industrial Solutions") == "d.main_routing"

        # Test sports sub-routing paths
        assert engine._find_decision_node_for_path(ctx, "Tennis Courts") == "d.sports_type"
        assert engine._find_decision_node_for_path(ctx, "Football Fields") == "d.sports_type"

    def test_luminárias_flow_path_finding(self):
        """Test the specific bug case from luminárias flow."""
        flow = self.create_luminárias_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Test main routing paths - these should go to d.roteamento_principal
        assert engine._find_decision_node_for_path(ctx, "Posto de gasolina") == "d.roteamento_principal"
        assert engine._find_decision_node_for_path(ctx, "Ginásio/Quadra") == "d.roteamento_principal"

        # Test quadra sub-routing paths - these should go to d.cobertura_quadra
        assert engine._find_decision_node_for_path(ctx, "Quadra coberta") == "d.cobertura_quadra"
        assert engine._find_decision_node_for_path(ctx, "Quadra descoberta") == "d.cobertura_quadra"

    def test_case_insensitive_path_matching(self):
        """Test that path matching works with different cases."""
        flow = self.create_multi_decision_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Test various case combinations
        assert engine._find_decision_node_for_path(ctx, "lighting solutions") == "d.main_routing"
        assert engine._find_decision_node_for_path(ctx, "SPORTS FACILITIES") == "d.main_routing"
        assert engine._find_decision_node_for_path(ctx, "Tennis courts") == "d.sports_type"
        assert engine._find_decision_node_for_path(ctx, "FOOTBALL FIELDS") == "d.sports_type"

    def test_partial_path_matching(self):
        """Test that partial path names still match correctly."""
        flow = self.create_luminárias_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Test partial matches
        assert engine._find_decision_node_for_path(ctx, "ginásio") == "d.roteamento_principal"
        assert engine._find_decision_node_for_path(ctx, "quadra") == "d.roteamento_principal"  # Should match first occurrence
        assert engine._find_decision_node_for_path(ctx, "posto") == "d.roteamento_principal"

    def test_nonexistent_path_returns_none(self):
        """Test that non-existent paths return None."""
        flow = self.create_multi_decision_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Test paths that don't exist
        assert engine._find_decision_node_for_path(ctx, "Nonexistent Path") is None
        assert engine._find_decision_node_for_path(ctx, "Random Stuff") is None
        assert engine._find_decision_node_for_path(ctx, "") is None

    def test_fallback_behavior_with_no_path(self):
        """Test fallback behavior when no specific path is provided."""
        flow = self.create_multi_decision_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Should return first decision node found (fallback behavior)
        result = engine._find_decision_node_for_path(ctx, None)
        assert result in ["d.main_routing", "d.sports_type"]  # Either is acceptable for fallback

    def test_empty_flow_returns_none(self):
        """Test behavior with flow that has no decision nodes."""
        flow = Flow(
            id="empty_flow",
            entry="q.only",
            nodes=[
                QuestionNode(id="q.only", kind="Question", key="only", prompt="Only question?"),
                TerminalNode(id="t.end", kind="Terminal", reason="Done")
            ],
            edges=[
                Edge(source="q.only", target="t.end", guard=GuardRef(fn="always"), priority=0)
            ]
        )

        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Should return None since there are no decision nodes
        assert engine._find_decision_node_for_path(ctx, "Any Path") is None
        assert engine._find_decision_node_for_path(ctx, None) is None

    def test_decision_node_without_condition_descriptions(self):
        """Test decision node that has no condition descriptions."""
        flow = Flow(
            id="no_conditions_flow",
            entry="q.start",
            nodes=[
                QuestionNode(id="q.start", kind="Question", key="start", prompt="Start?"),
                DecisionNode(id="d.no_conditions", kind="Decision", label="No conditions"),
                QuestionNode(id="q.next", kind="Question", key="next", prompt="Next?"),
                TerminalNode(id="t.end", kind="Terminal", reason="Done")
            ],
            edges=[
                Edge(source="q.start", target="d.no_conditions", guard=GuardRef(fn="always"), priority=0),
                # Edge without condition_description
                Edge(source="d.no_conditions", target="q.next", guard=GuardRef(fn="always"), priority=0),
                Edge(source="q.next", target="t.end", guard=GuardRef(fn="always"), priority=0),
            ]
        )

        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Should return None since decision node has no condition descriptions
        assert engine._find_decision_node_for_path(ctx, "Any Path") is None
        assert engine._find_decision_node_for_path(ctx, None) is None

    def test_multiple_matching_paths_returns_first(self):
        """Test that when multiple decision nodes could match, it returns the first valid one."""
        flow = Flow(
            id="multiple_matches",
            entry="q.start",
            nodes=[
                QuestionNode(id="q.start", kind="Question", key="start", prompt="Start?"),
                DecisionNode(id="d.first", kind="Decision", label="First decision"),
                DecisionNode(id="d.second", kind="Decision", label="Second decision"),
                QuestionNode(id="q.sports1", kind="Question", key="sports1", prompt="Sports 1?"),
                QuestionNode(id="q.sports2", kind="Question", key="sports2", prompt="Sports 2?"),
                TerminalNode(id="t.end", kind="Terminal", reason="Done")
            ],
            edges=[
                Edge(source="q.start", target="d.first", guard=GuardRef(fn="always"), priority=0),
                Edge(source="d.first", target="d.second", guard=GuardRef(fn="always"), priority=0),

                # Both decision nodes have "Sports" paths
                Edge(
                    source="d.first",
                    target="q.sports1",
                    guard=GuardRef(fn="always"),
                    priority=1,
                    condition_description="Sports Option A"
                ),
                Edge(
                    source="d.second",
                    target="q.sports2",
                    guard=GuardRef(fn="always"),
                    priority=0,
                    condition_description="Sports Option B"
                ),

                Edge(source="q.sports1", target="t.end", guard=GuardRef(fn="always"), priority=0),
                Edge(source="q.sports2", target="t.end", guard=GuardRef(fn="always"), priority=0),
            ]
        )

        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Should find the first decision node that matches "Sports"
        result = engine._find_decision_node_for_path(ctx, "Sports Option A")
        assert result == "d.first"

        result = engine._find_decision_node_for_path(ctx, "Sports Option B")
        assert result == "d.second"

    def test_edge_cases_and_malformed_data(self):
        """Test edge cases and malformed data handling."""
        flow = self.create_multi_decision_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Test with None path
        assert engine._find_decision_node_for_path(ctx, None) is not None  # Should use fallback

        # Test with empty string
        assert engine._find_decision_node_for_path(ctx, "") is None

        # Test with whitespace only
        assert engine._find_decision_node_for_path(ctx, "   ") is None

        # Test with very long string
        long_path = "x" * 1000
        assert engine._find_decision_node_for_path(ctx, long_path) is None

    def test_real_world_scenario_path_correction(self):
        """Test the real-world scenario that caused the original bug."""
        flow = self.create_luminárias_flow()
        engine = self.setup_engine(flow)
        ctx = FlowContext("test")

        # Simulate the original bug scenario:
        # User was on "Posto de gasolina" path, then corrected to "Ginásio/Quadra"

        # First, user selects posto path
        posto_decision = engine._find_decision_node_for_path(ctx, "Posto de gasolina")
        assert posto_decision == "d.roteamento_principal"

        # Then user corrects to ginásio path
        ginasio_decision = engine._find_decision_node_for_path(ctx, "Ginásio/Quadra")
        assert ginasio_decision == "d.roteamento_principal"

        # Both should return the same decision node (the main routing one)
        assert posto_decision == ginasio_decision

        # But different from the sub-decision node
        quadra_decision = engine._find_decision_node_for_path(ctx, "Quadra coberta")
        assert quadra_decision == "d.cobertura_quadra"
        assert quadra_decision != ginasio_decision


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
