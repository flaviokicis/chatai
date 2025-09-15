#!/bin/bash
# Quick launcher for WhatsApp CLI

cd "$(dirname "$0")"  # Ensure we're in backend directory
source .venv/bin/activate

if [ "$1" == "--list" ]; then
    python -m app.flow_core.whatsapp_cli --list-channels
elif [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    python -m app.flow_core.whatsapp_cli --help
elif [ -n "$1" ]; then
    # If argument provided, use it as phone number
    python -m app.flow_core.whatsapp_cli --phone "$1"
else
    # Default to GlixLeds
    echo "Connecting to GlixLeds WhatsApp..."
    python -m app.flow_core.whatsapp_cli --phone +15550489424
fi
