#!/usr/bin/env python3
"""Quick script to update debouncing wait time for testing."""

from app.db.session import get_db_session
from app.db.models import TenantProjectConfig

# Change this value as needed
NEW_WAIT_TIME_MS = 15000  # 15 seconds for faster testing

with next(get_db_session()) as session:
    configs = session.query(TenantProjectConfig).all()
    
    print(f"Updating wait_time_before_replying_ms to {NEW_WAIT_TIME_MS}ms for {len(configs)} tenant(s)...")
    
    for config in configs:
        old_value = config.wait_time_before_replying_ms
        config.wait_time_before_replying_ms = NEW_WAIT_TIME_MS
        print(f"  Tenant {config.tenant_id}: {old_value}ms → {NEW_WAIT_TIME_MS}ms")
    
    session.commit()
    print(f"✅ Done! All tenants now have {NEW_WAIT_TIME_MS}ms wait time.")
    print("\n💡 To revert to production (60s), change NEW_WAIT_TIME_MS = 60000 and re-run.")

