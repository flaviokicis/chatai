#!/bin/bash
# Test script for WhatsApp Simulator CLI - Production Mode

echo "================================================"
echo "WhatsApp Simulator CLI - Production Mode Test"
echo "================================================"

# Activate virtual environment
source .venv/bin/activate

echo ""
echo "📱 Available WhatsApp Channels:"
echo "================================================"
python -m app.flow_core.whatsapp_cli --list-channels

echo ""
echo "To connect to a specific channel, run:"
echo "  python -m app.flow_core.whatsapp_cli --phone <NUMBER>"
echo ""
echo "Example (GlixLeds):"
echo "  python -m app.flow_core.whatsapp_cli --phone 674436192430525"
echo ""
echo "Example with custom flow:"
echo "  python -m app.flow_core.whatsapp_cli --phone 674436192430525 --flow playground/fluxo_luminarias.json"
