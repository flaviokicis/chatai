#!/usr/bin/env python
"""
Script to clean up duplicate contacts in the database.

This script identifies and merges duplicate contacts that have the same
external_id (after decryption), keeping the oldest contact and consolidating
all threads under it.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import ChatThread, Contact
from app.db.session import db_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_duplicate_contacts():
    """Clean up duplicate contacts by merging them."""
    
    with db_session() as session:
        # Get all active contacts
        contacts = session.execute(
            select(Contact).where(Contact.deleted_at.is_(None))
            .order_by(Contact.created_at.asc())
        ).scalars().all()
        
        logger.info(f"Found {len(contacts)} total active contacts")
        
        # Group contacts by tenant_id and decrypted external_id
        contact_groups = defaultdict(list)
        
        for contact in contacts:
            try:
                # Create a key based on tenant_id and decrypted external_id
                key = (contact.tenant_id, contact.external_id)
                contact_groups[key].append(contact)
            except Exception as e:
                logger.warning(f"Could not process contact {contact.id}: {e}")
                continue
        
        # Find groups with duplicates
        duplicate_groups = {k: v for k, v in contact_groups.items() if len(v) > 1}
        
        if not duplicate_groups:
            logger.info("No duplicate contacts found!")
            return
        
        logger.info(f"Found {len(duplicate_groups)} groups with duplicates")
        
        total_duplicates_removed = 0
        total_threads_migrated = 0
        
        for (tenant_id, external_id), contacts_list in duplicate_groups.items():
            # Sort by creation date - keep the oldest
            contacts_list.sort(key=lambda c: c.created_at)
            keep_contact = contacts_list[0]
            duplicate_contacts = contacts_list[1:]
            
            logger.info(f"Processing duplicates for {external_id[:20]}...")
            logger.info(f"  Keeping contact: {keep_contact.id} (created: {keep_contact.created_at})")
            logger.info(f"  Removing {len(duplicate_contacts)} duplicates")
            
            # Migrate all threads from duplicate contacts to the keeper
            for dup_contact in duplicate_contacts:
                # Find all threads for this duplicate contact
                threads = session.execute(
                    select(ChatThread).where(
                        ChatThread.contact_id == dup_contact.id,
                        ChatThread.deleted_at.is_(None)
                    )
                ).scalars().all()
                
                if threads:
                    logger.info(f"    Migrating {len(threads)} threads from {dup_contact.id}")
                    for thread in threads:
                        # Check if a thread already exists for the keeper contact with same channel
                        existing_thread = session.execute(
                            select(ChatThread).where(
                                ChatThread.tenant_id == thread.tenant_id,
                                ChatThread.channel_instance_id == thread.channel_instance_id,
                                ChatThread.contact_id == keep_contact.id,
                                ChatThread.deleted_at.is_(None)
                            )
                        ).scalar_one_or_none()
                        
                        if existing_thread:
                            # Thread already exists for keeper, mark duplicate as deleted
                            thread.deleted_at = datetime.now(UTC)
                            logger.info(f"      Marking duplicate thread {thread.id} as deleted")
                        else:
                            # Migrate thread to keeper contact
                            thread.contact_id = keep_contact.id
                            total_threads_migrated += 1
                            logger.info(f"      Migrated thread {thread.id} to keeper contact")
                
                # Mark duplicate contact as deleted
                dup_contact.deleted_at = datetime.now(UTC)
                total_duplicates_removed += 1
        
        # Commit all changes
        session.commit()
        
        logger.info("=" * 60)
        logger.info("CLEANUP COMPLETED SUCCESSFULLY!")
        logger.info(f"  Duplicate contacts removed: {total_duplicates_removed}")
        logger.info(f"  Threads migrated: {total_threads_migrated}")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        cleanup_duplicate_contacts()
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
