#!/bin/bash
# Test script for WhatsApp Simulator CLI

echo "================================================"
echo "WhatsApp Simulator CLI Test"
echo "================================================"

# Activate virtual environment
source .venv/bin/activate

# Test with a flow file
echo "Starting WhatsApp simulator with flow example..."
python -m app.flow_core.whatsapp_cli playground/flow_example.json --model gpt-5

# Alternative: Use the wrapper script
# ./whatsapp_cli.py playground/flow_example.json --model gpt-5

# Optional: Reset to create new tenant/channel
# python -m app.flow_core.whatsapp_cli playground/flow_example.json --model gpt-5 --reset
