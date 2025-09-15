#!/usr/bin/env python3
"""
WhatsApp CLI Launcher - Wrapper to properly run the CLI with correct imports
"""

import subprocess
import sys
from pathlib import Path

# Run the CLI module properly
backend_dir = Path(__file__).parent
cli_module = "app.flow_core.whatsapp_cli"

# Pass through all arguments
args = [sys.executable, "-m", cli_module] + sys.argv[1:]

# Run from backend directory
subprocess.run(args, check=False, cwd=backend_dir)
