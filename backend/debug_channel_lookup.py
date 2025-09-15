#!/usr/bin/env python3
"""
Debug script to understand channel lookup issue.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from app.db.models import ChannelInstance
from app.db.repository import find_channel_instance_by_identifier
from app.db.session import db_session


def debug_lookup():
    """Debug channel lookup."""
    phone = "+15550489424"
    
    with db_session() as session:
        print(f"🔍 Looking for: {phone}")
        
        # Method 1: find_channel_instance_by_identifier
        identifier = f"whatsapp:{phone}"
        print(f"\n1. Trying find_channel_instance_by_identifier with: {identifier}")
        channel = find_channel_instance_by_identifier(session, identifier)
        print(f"   Result: {channel}")
        
        # Method 2: Direct query by phone_number
        print(f"\n2. Trying direct query by phone_number = '{phone}'")
        channel = session.query(ChannelInstance).filter(
            ChannelInstance.phone_number == phone
        ).first()
        print(f"   Result: {channel}")
        
        # Method 3: Show all channels with details
        print("\n3. All channels in database:")
        channels = session.query(ChannelInstance).all()
        for ch in channels:
            print(f"\n   Channel ID: {ch.id}")
            print(f"   Identifier: {ch.identifier}")
            print(f"   Phone Number (encrypted field): {ch.phone_number}")
            print(f"   Raw Phone Number: {ch.phone_number!r}")
            
            # Try different comparisons
            print(f"   phone == ch.phone_number: {phone == ch.phone_number}")
            print(f"   phone in str(ch.phone_number): {phone in str(ch.phone_number) if ch.phone_number else False}")

if __name__ == "__main__":
    debug_lookup()
