"""Integration tests that use real database and flow validation."""



# Example of a REAL integration test (uncomment to use)
"""
@pytest.mark.integration
def test_pain_scale_update_real_database():
    '''Test pain scale update with real database operations.'''
    session = create_session()
    
    try:
        # Create a real flow in the database
        flow = create_flow(
            session,
            tenant_id=uuid4(),
            channel_instance_id=uuid4(), 
            name="Test Dentist Flow",
            flow_id="test.dentist",
            definition={
                "schema_version": "v1",
                "id": "test.dentist",
                "entry": "q.intensidade_dor",
                "nodes": [
                    {
                        "id": "q.intensidade_dor",
                        "key": "intensidade_dor",
                        "kind": "Question",
                        "prompt": "Em uma escala de 1 a 10, qual a intensidade da sua dor?",
                        "allowed_values": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
                    }
                ],
                "edges": []
            }
        )
        session.commit()
        
        # Get the flow definition
        db_flow = get_flow_by_id(session, flow.id)
        flow_def = db_flow.definition
        
        # REAL update with REAL database
        result = update_node(
            flow_definition=flow_def,
            node_id="q.intensidade_dor",
            updates={
                "prompt": "Em uma escala de 1 a 5, qual a intensidade da sua dor?", 
                "allowed_values": ["1", "2", "3", "4", "5"]
            },
            user_message="Real database test!",
            flow_id=flow.id,
            session=session
        )
        session.commit()
        
        # Verify the change was persisted to real database
        updated_flow = get_flow_by_id(session, flow.id)
        pain_node = next(node for node in updated_flow.definition["nodes"] 
                        if node["id"] == "q.intensidade_dor")
        
        assert pain_node["allowed_values"] == ["1", "2", "3", "4", "5"]
        assert "Real database test!" in result
        
    finally:
        session.rollback()  # Clean up
        session.close()
"""


if __name__ == "__main__":
    print("Integration tests are commented out.")
    print("To run real database tests, uncomment the test function and run:")
    print("pytest tests/test_flow_integration.py::test_pain_scale_update_real_database -v")
