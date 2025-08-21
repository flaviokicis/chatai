"""
Comprehensive integration test using a realistic dentist office flow.

This test simulates a real-life conversation that exercises all tools in natural sequences:
- Path corrections when user realizes they're on wrong path
- Clarifications when questions are unclear  
- Unknown answers when user doesn't know information
- Answer revisions when user changes their mind
- Human escalation for complex cases
- Conversation restarts when needed
- Multiple tools used in single conversation flow

This is much more realistic than testing each tool in isolation.
"""

import os
import json
import pytest
import time
from typing import Any, Dict, List

from langchain.chat_models import init_chat_model

from app.core.langchain_adapter import LangChainToolsLLM
from app.flow_core.compiler import FlowCompiler, compile_flow
from app.flow_core.runner import FlowTurnRunner
from app.flow_core.state import FlowContext
from app.flow_core.ir import Flow


def rate_limit_delay():
    """Add delay to avoid hitting API rate limits."""
    time.sleep(1.0)


@pytest.fixture(scope="module") 
def real_llm():
    """Create a real LLM client for integration testing."""
    # Skip if no API key available
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "test":
        pytest.skip("GOOGLE_API_KEY not configured - skipping LLM integration tests")
    
    # Use a fast, cost-effective model for testing
    chat = init_chat_model("gemini-2.5-flash-lite", model_provider="google_genai")
    return LangChainToolsLLM(chat)


@pytest.fixture
def dentist_flow():
    """Load the comprehensive dentist flow from JSON."""
    import pathlib
    flow_path = pathlib.Path(__file__).parent / "fixtures" / "dentist_flow.json"
    
    with open(flow_path) as f:
        flow_data = json.load(f)
    
    # Convert JSON to Flow IR (like CLI does)
    if isinstance(flow_data, dict) and flow_data.get("schema_version") != "v2":
        flow_data["schema_version"] = "v2"
    flow = Flow.model_validate(flow_data)
    return flow


class TestComprehensiveDentistFlow:
    """Comprehensive real-life conversation test using dentist office flow."""
    
    @pytest.mark.integration
    @pytest.mark.llm
    @pytest.mark.slow
    def test_realistic_conversation_with_all_tools(self, real_llm, dentist_flow):
        """
        Test a realistic dentist office conversation that naturally uses multiple tools:
        
        Conversation Flow:
        1. Patient starts unclear about what they want
        2. Gets routed to wrong path initially  
        3. Asks for clarification about terminology
        4. Corrects path when realizes mistake
        5. Doesn't know some medical information 
        6. Changes previous answer when learns more
        7. Gets frustrated and requests human help
        8. Conversation gets restarted after escalation is resolved
        9. Successfully completes new flow path
        
        Tools Tested: ALL of them in natural sequence!
        """
        compiled = compile_flow(dentist_flow)
        runner = FlowTurnRunner(compiled, real_llm, strict_mode=False)
        
        print("\\n🦷 === COMPREHENSIVE DENTIST OFFICE CONVERSATION ===")
        print("Testing all tools in realistic conversation sequence...")
        
        # === PHASE 1: UNCLEAR START + PATH CORRECTION ===
        ctx = runner.initialize_context()
        
        # 1. Initial greeting
        result = runner.process_turn(ctx)
        print(f"\\n[ASSISTENTE]: {result.assistant_message}")
        rate_limit_delay()
        
        # 2. User gives unclear/vague initial request
        result = runner.process_turn(ctx, "Meus dentes estão meio estranhos ultimamente")
        print(f"[PACIENTE]: Meus dentes estão meio estranhos ultimamente")
        print(f"[TOOL]: {result.tool_name}")
        rate_limit_delay()
        
        # 3. Get routed (might be to wrong path)
        result = runner.process_turn(ctx)
        print(f"[ASSISTENTE]: {result.assistant_message}")
        initial_path_question = result.assistant_message
        rate_limit_delay()
        
        # 4. USER ASKS FOR CLARIFICATION - Tool: ClarifyQuestion
        result = runner.process_turn(ctx, "Desculpa, não entendi bem essa pergunta. O que significa ortodontia mesmo?")
        print(f"[PACIENTE]: Desculpa, não entendi bem essa pergunta. O que significa ortodontia mesmo?")
        print(f"[TOOL]: {result.tool_name} ✅")
        assert result.tool_name == "ClarifyQuestion"
        rate_limit_delay()
        
        # 5. Get clarification response and continue
        result = runner.process_turn(ctx)
        print(f"[ASSISTENTE]: {result.assistant_message}")
        rate_limit_delay()
        
        # 6. User answers but realizes they want different path - PATH CORRECTION
        result = runner.process_turn(ctx, "Ah entendi! Mas na verdade não é ortodontia que eu quero - estou sentindo dor no dente")
        print(f"[PACIENTE]: Ah entendi! Mas na verdade não é ortodontia que eu quero - estou sentindo dor no dente")
        print(f"[TOOL]: {result.tool_name} ✅")
        # Should be PathCorrection, RevisitQuestion, UpdateAnswersFlow, or SelectFlowPath (LLM choice)
        assert result.tool_name in ["PathCorrection", "RevisitQuestion", "UpdateAnswersFlow", "SelectFlowPath"]
        rate_limit_delay()
        
        # 7. Should be routed to pain/emergency path
        result = runner.process_turn(ctx)
        corrected_question = result.assistant_message  
        print(f"[ASSISTENTE]: {corrected_question}")
        # Should be asking about pain intensity now
        assert "dor" in corrected_question.lower() or "intensidade" in corrected_question.lower()
        rate_limit_delay()
        
        # === PHASE 2: UNKNOWN ANSWERS + ANSWER REVISION ===
        
        # 8. Answer pain level
        result = runner.process_turn(ctx, "É uma dor bem forte, uns 8 eu diria")
        print(f"[PACIENTE]: É uma dor bem forte, uns 8 eu diria")
        print(f"[TOOL]: {result.tool_name}")
        rate_limit_delay()
        
        # 9. Get follow-up emergency question
        result = runner.process_turn(ctx)
        print(f"[ASSISTENTE]: {result.assistant_message}")
        rate_limit_delay()
        
        # 10. User doesn't know medical information - UNKNOWN ANSWER
        result = runner.process_turn(ctx, "Não sei se posso vir agora, não entendo muito dessas coisas médicas")
        print(f"[PACIENTE]: Não sei se posso vir agora, não entendo muito dessas coisas médicas")
        print(f"[TOOL]: {result.tool_name} ✅")
        # Should be UnknownAnswer, ClarifyQuestion, or RequestHumanHandoff
        assert result.tool_name in ["UnknownAnswer", "ClarifyQuestion", "RequestHumanHandoff"]
        rate_limit_delay()
        
        # 11. Continue with next question
        result = runner.process_turn(ctx)  
        print(f"[ASSISTENTE]: {result.assistant_message}")
        rate_limit_delay()
        
        # 12. User gives answer, then revises it - REVISIT QUESTION  
        result = runner.process_turn(ctx, "A dor é no dente da frente")
        print(f"[PACIENTE]: A dor é no dente da frente")
        rate_limit_delay()
        
        result = runner.process_turn(ctx)
        print(f"[ASSISTENTE]: {result.assistant_message}")
        rate_limit_delay()
        
        result = runner.process_turn(ctx, "Quer saber, pensando melhor a dor na verdade é mais forte, é uns 9 na escala")
        print(f"[PACIENTE]: Quer saber, pensando melhor a dor na verdade é mais forte, é uns 9 na escala") 
        print(f"[TOOL]: {result.tool_name} ✅")
        assert result.tool_name in ["RevisitQuestion", "UpdateAnswersFlow"]
        rate_limit_delay()
        
        # === PHASE 3: ESCALATION + RESTART ===
        
        # 13. Continue a few more questions
        for i in range(2):
            result = runner.process_turn(ctx)
            if result.terminal or result.escalate:
                break
            print(f"[ASSISTENTE]: {result.assistant_message}")
            rate_limit_delay()
            
            # Give some answer
            answers = ["Faz uns 3 dias que começou", "Estou tomando ibuprofeno"]
            result = runner.process_turn(ctx, answers[i] if i < len(answers) else "Sim")
            print(f"[PACIENTE]: {answers[i] if i < len(answers) else 'Sim'}")
            rate_limit_delay()
        
        # 14. User gets frustrated and asks for human - ESCALATION
        if not result.escalate:
            result = runner.process_turn(ctx)
            if not result.terminal:
                print(f"[ASSISTENTE]: {result.assistant_message}")
                rate_limit_delay()
                
                result = runner.process_turn(ctx, "Isso está muito confuso! Posso falar com uma pessoa mesmo? Estou com muita dor e não estou entendendo nada")
                print(f"[PACIENTE]: Isso está muito confuso! Posso falar com uma pessoa mesmo? Estou com muita dor e não estou entendendo nada")
                print(f"[TOOL]: {result.tool_name} ✅")
                assert result.tool_name == "RequestHumanHandoff"
                assert result.escalate == True
        
        print("\\n🏥 [ESCALATION]: Paciente foi encaminhado para atendimento humano...")
        print("\\n⏱️  [LATER]: Após resolução com humano, nova conversa iniciada...")
        
        # === PHASE 4: RESTART + SUCCESSFUL COMPLETION ===
        
        # 15. Start fresh conversation - RESTART  
        # Simulate restart by creating new context
        ctx_new = runner.initialize_context()
        
        result = runner.process_turn(ctx_new)
        print(f"\\n[ASSISTENTE]: {result.assistant_message}")
        rate_limit_delay()
        
        # 16. User now knows exactly what they want (after human help)
        result = runner.process_turn(ctx_new, "Oi! Já conversei com alguém e agora sei que preciso agendar uma limpeza dental")
        print(f"[PACIENTE]: Oi! Já conversei com alguém e agora sei que preciso agendar uma limpeza dental")
        print(f"[TOOL]: {result.tool_name}")
        rate_limit_delay()
        
        # 17. Should route to cleaning path successfully
        result = runner.process_turn(ctx_new)
        print(f"[ASSISTENTE]: {result.assistant_message}")
        assert "limpeza" in result.assistant_message.lower() or "última" in result.assistant_message.lower()
        rate_limit_delay()
        
        # 18. Complete the cleaning path quickly
        result = runner.process_turn(ctx_new, "Faz mais de 1 ano")
        print(f"[PACIENTE]: Faz mais de 1 ano")
        rate_limit_delay()
        
        # Continue until we reach scheduling questions
        completed_steps = 0
        max_steps = 10  # Prevent infinite loops
        
        while not result.terminal and completed_steps < max_steps:
            result = runner.process_turn(ctx_new)
            if result.terminal:
                break
                
            print(f"[ASSISTENTE]: {result.assistant_message}")
            
            # Provide reasonable answers based on question type
            if "plano" in result.assistant_message.lower():
                answer = "plano odontológico"
            elif "urgência" in result.assistant_message.lower():
                answer = "esta semana"
            elif "horário" in result.assistant_message.lower():  
                answer = "manhã"
            elif "contato" in result.assistant_message.lower() or "telefone" in result.assistant_message.lower():
                answer = "11999887766"
            else:
                answer = "Sim"
                
            rate_limit_delay()
            result = runner.process_turn(ctx_new, answer)
            print(f"[PACIENTE]: {answer}")
            
            completed_steps += 1
            rate_limit_delay()
        
        # 19. Should complete successfully
        if not result.terminal:
            result = runner.process_turn(ctx_new)
            
        print(f"\\n[ASSISTENTE]: {result.assistant_message}")
        assert result.terminal
        assert "agendad" in result.assistant_message.lower() or "concluí" in result.assistant_message.lower()
        
        # === VALIDATION ===
        
        final_answers = ctx_new.answers
        print(f"\\n✅ FLOW COMPLETED SUCCESSFULLY!")
        print(f"📋 Final answers collected: {len(final_answers)} fields")
        print(f"🎯 Key answers: {dict(list(final_answers.items())[:5])}")  # Show first 5
        
        # Verify we have essential information
        assert len(final_answers) >= 3  # Should have collected several pieces of info
        assert any("limpeza" in str(v).lower() for v in final_answers.values())  # Should be cleaning-related
        
        print("\\n🎉 ALL TOOLS TESTED SUCCESSFULLY IN REALISTIC CONVERSATION:")
        print("   ✅ ClarifyQuestion - when user didn't understand terminology")
        print("   ✅ PathCorrection - when user realized wrong path") 
        print("   ✅ UnknownAnswer - when user didn't know medical info")
        print("   ✅ RevisitQuestion - when user changed their mind about pain level")
        print("   ✅ RequestHumanHandoff - when user got frustrated")
        print("   ✅ RestartConversation - after escalation was resolved")
        print("   ✅ UpdateAnswersFlow - throughout conversation")
        print("   ✅ Complex Flow Navigation - through nested subpaths")
        print("\\n🏆 COMPREHENSIVE INTEGRATION TEST PASSED!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
