#!/usr/bin/env python
"""
Improved script to clean up duplicate contacts in the database.
This version handles thread constraint violations better.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.db.models import ChatThread, Contact, Message
from app.db.session import db_transaction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_duplicate_contacts():
    """Clean up duplicate contacts by merging them carefully."""

    with db_transaction() as session:
        # Get all active contacts
        contacts = (
            session.execute(
                select(Contact)
                .where(Contact.deleted_at.is_(None))
                .order_by(Contact.created_at.asc())
            )
            .scalars()
            .all()
        )

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
        total_threads_deleted = 0
        total_messages_migrated = 0

        for (tenant_id, external_id), contacts_list in duplicate_groups.items():
            # Sort by creation date - keep the oldest
            contacts_list.sort(key=lambda c: c.created_at)
            keep_contact = contacts_list[0]
            duplicate_contacts = contacts_list[1:]

            logger.info(f"\nProcessing duplicates for {external_id[:30]}...")
            logger.info(
                f"  Keeping contact: {keep_contact.id} (created: {keep_contact.created_at})"
            )
            logger.info(f"  Removing {len(duplicate_contacts)} duplicates")

            for dup_contact in duplicate_contacts:
                # Find all threads for this duplicate contact
                dup_threads = (
                    session.execute(
                        select(ChatThread).where(
                            ChatThread.contact_id == dup_contact.id, ChatThread.deleted_at.is_(None)
                        )
                    )
                    .scalars()
                    .all()
                )

                for dup_thread in dup_threads:
                    # Check if keeper already has a thread for this channel
                    existing_thread = session.execute(
                        select(ChatThread).where(
                            ChatThread.tenant_id == dup_thread.tenant_id,
                            ChatThread.channel_instance_id == dup_thread.channel_instance_id,
                            ChatThread.contact_id == keep_contact.id,
                            ChatThread.deleted_at.is_(None),
                        )
                    ).scalar_one_or_none()

                    if existing_thread:
                        # Migrate messages from duplicate thread to existing thread
                        dup_messages = (
                            session.execute(
                                select(Message).where(Message.thread_id == dup_thread.id)
                            )
                            .scalars()
                            .all()
                        )

                        if dup_messages:
                            logger.info(
                                f"    Migrating {len(dup_messages)} messages from duplicate thread"
                            )
                            for msg in dup_messages:
                                msg.thread_id = existing_thread.id
                                msg.contact_id = keep_contact.id
                                total_messages_migrated += 1

                        # Mark duplicate thread as deleted
                        dup_thread.deleted_at = datetime.now(UTC)
                        total_threads_deleted += 1
                        logger.info(f"    Deleted duplicate thread {dup_thread.id}")
                    else:
                        # No existing thread, migrate this one
                        logger.info(f"    Migrating thread {dup_thread.id} to keeper contact")
                        dup_thread.contact_id = keep_contact.id

                        # Also update all messages in this thread
                        session.execute(
                            update(Message)
                            .where(Message.thread_id == dup_thread.id)
                            .values(contact_id=keep_contact.id)
                        )
                        total_threads_migrated += 1

                # Mark duplicate contact as deleted
                dup_contact.deleted_at = datetime.now(UTC)
                total_duplicates_removed += 1
                logger.info(f"  Marked duplicate contact {dup_contact.id} as deleted")

        # Commit is automatic with db_transaction

        logger.info("\n" + "=" * 60)
        logger.info("CLEANUP COMPLETED SUCCESSFULLY!")
        logger.info(f"  Duplicate contacts removed: {total_duplicates_removed}")
        logger.info(f"  Threads migrated: {total_threads_migrated}")
        logger.info(f"  Duplicate threads deleted: {total_threads_deleted}")
        logger.info(f"  Messages migrated: {total_messages_migrated}")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        cleanup_duplicate_contacts()
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
