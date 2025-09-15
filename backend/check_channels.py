#!/usr/bin/env python3
"""
Script to check all channels and look for a specific phone number in various formats.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from app.db.models import ChannelInstance
from app.db.session import db_session


def check_channels():
    """Check all channels and look for the phone number."""
    target_number = "15550489424"

    with db_session() as session:
        channels = session.query(ChannelInstance).all()

        print(f"🔍 Looking for number containing: {target_number}")
        print(f"Total channels in database: {len(channels)}\n")

        print("All channels:")
        for channel in channels:
            # Clean the identifier
            identifier = channel.identifier.replace("whatsapp:", "")
            clean_number = "".join(c for c in identifier if c.isdigit())

            print(f"  • Identifier: {channel.identifier}")
            print(f"    Clean number: {clean_number}")
            print(f"    Phone field: {channel.phone_number}")
            print(f"    Tenant: {channel.tenant.owner_first_name} {channel.tenant.owner_last_name}")

            # Check if this matches our target
            if target_number in clean_number or clean_number in target_number:
                print("    ⚠️  POSSIBLE MATCH!")

            print()


if __name__ == "__main__":
    check_channels()
