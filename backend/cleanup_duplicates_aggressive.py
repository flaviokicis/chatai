#!/usr/bin/env python
"""
Aggressive cleanup script for duplicate contacts and threads.
This version handles all constraint issues by merging threads properly.
"""

import logging
from collections import defaultdict

from sqlalchemy import text

from app.db.session import get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def aggressive_cleanup():
    """Aggressively clean up all duplicate contacts and threads."""

    engine = get_engine()

    with engine.begin() as conn:
        # Step 1: Find all duplicate contacts (same external_id after decryption)
        logger.info("Step 1: Finding duplicate contacts...")

        # Get all contacts with their decrypted external_ids
        result = conn.execute(
            text("""
            SELECT id, tenant_id, external_id, created_at, deleted_at
            FROM contacts
            WHERE deleted_at IS NULL
            ORDER BY created_at ASC
        """)
        )

        all_contacts = result.fetchall()
        logger.info(f"Found {len(all_contacts)} total active contacts")

        # We need to decrypt and group them
        # Since we can't decrypt in SQL, we'll use Python
        from app.db.types import _get_fernet

        try:
            fernet = _get_fernet()
            contact_groups = defaultdict(list)

            for (
                contact_id,
                tenant_id,
                encrypted_external_id,
                created_at,
                deleted_at,
            ) in all_contacts:
                try:
                    # Decrypt the external_id
                    decrypted_external_id = fernet.decrypt(bytes(encrypted_external_id)).decode(
                        "utf-8"
                    )
                    key = (tenant_id, decrypted_external_id)
                    contact_groups[key].append(
                        {
                            "id": contact_id,
                            "created_at": created_at,
                            "external_id": decrypted_external_id,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Could not decrypt contact {contact_id}: {e}")
                    continue

            # Find groups with duplicates
            duplicate_groups = {k: v for k, v in contact_groups.items() if len(v) > 1}
            logger.info(f"Found {len(duplicate_groups)} groups with duplicate contacts")

            if not duplicate_groups:
                logger.info("No duplicates found!")
                return

            total_contacts_deleted = 0
            total_threads_merged = 0
            total_threads_deleted = 0
            total_messages_migrated = 0

            for (tenant_id, external_id), contacts in duplicate_groups.items():
                # Sort by creation date - keep the oldest
                contacts.sort(key=lambda c: c["created_at"])
                keeper = contacts[0]
                duplicates = contacts[1:]

                logger.info(f"\nProcessing {external_id[:30]}...")
                logger.info(f"  Keeper: {keeper['id']} (created {keeper['created_at']})")
                logger.info(f"  Removing {len(duplicates)} duplicates")

                keeper_id = keeper["id"]

                for dup in duplicates:
                    dup_id = dup["id"]

                    # Step 2: Find all threads for the duplicate contact
                    threads_result = conn.execute(
                        text("""
                        SELECT id, channel_instance_id 
                        FROM chat_threads 
                        WHERE contact_id = :contact_id 
                        AND deleted_at IS NULL
                    """),
                        {"contact_id": dup_id},
                    )

                    dup_threads = threads_result.fetchall()

                    for thread_id, channel_id in dup_threads:
                        # Check if keeper already has a thread for this channel
                        existing_thread_result = conn.execute(
                            text("""
                            SELECT id 
                            FROM chat_threads 
                            WHERE tenant_id = :tenant_id
                            AND channel_instance_id = :channel_id
                            AND contact_id = :contact_id
                            AND deleted_at IS NULL
                            LIMIT 1
                        """),
                            {
                                "tenant_id": tenant_id,
                                "channel_id": channel_id,
                                "contact_id": keeper_id,
                            },
                        )

                        existing_thread = existing_thread_result.fetchone()

                        if existing_thread:
                            # Keeper already has a thread for this channel
                            existing_thread_id = existing_thread[0]

                            # Migrate all messages from duplicate thread to existing thread
                            message_result = conn.execute(
                                text("""
                                UPDATE messages 
                                SET thread_id = :new_thread_id,
                                    contact_id = :new_contact_id
                                WHERE thread_id = :old_thread_id
                                RETURNING id
                            """),
                                {
                                    "new_thread_id": existing_thread_id,
                                    "new_contact_id": keeper_id,
                                    "old_thread_id": thread_id,
                                },
                            )

                            migrated_count = message_result.rowcount
                            total_messages_migrated += migrated_count

                            if migrated_count > 0:
                                logger.info(
                                    f"    Migrated {migrated_count} messages to existing thread"
                                )

                            # Delete the duplicate thread
                            conn.execute(
                                text("""
                                UPDATE chat_threads 
                                SET deleted_at = NOW() 
                                WHERE id = :thread_id
                            """),
                                {"thread_id": thread_id},
                            )

                            total_threads_deleted += 1
                            logger.info(f"    Deleted duplicate thread {thread_id}")

                        else:
                            # No existing thread, migrate this one to keeper
                            conn.execute(
                                text("""
                                UPDATE chat_threads 
                                SET contact_id = :new_contact_id 
                                WHERE id = :thread_id
                            """),
                                {"new_contact_id": keeper_id, "thread_id": thread_id},
                            )

                            # Also update all messages in this thread
                            conn.execute(
                                text("""
                                UPDATE messages 
                                SET contact_id = :new_contact_id 
                                WHERE thread_id = :thread_id
                            """),
                                {"new_contact_id": keeper_id, "thread_id": thread_id},
                            )

                            total_threads_merged += 1
                            logger.info(f"    Migrated thread {thread_id} to keeper")

                    # Step 3: Mark duplicate contact as deleted
                    conn.execute(
                        text("""
                        UPDATE contacts 
                        SET deleted_at = NOW() 
                        WHERE id = :contact_id
                    """),
                        {"contact_id": dup_id},
                    )

                    total_contacts_deleted += 1
                    logger.info(f"  Deleted duplicate contact {dup_id}")

            logger.info("\n" + "=" * 60)
            logger.info("AGGRESSIVE CLEANUP COMPLETED!")
            logger.info(f"  Duplicate contacts deleted: {total_contacts_deleted}")
            logger.info(f"  Threads merged to keeper: {total_threads_merged}")
            logger.info(f"  Duplicate threads deleted: {total_threads_deleted}")
            logger.info(f"  Messages migrated: {total_messages_migrated}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Failed to get encryption key: {e}")
            logger.info("\nFalling back to simple cleanup based on phone numbers...")

            # Fallback: Just mark obvious test duplicates as deleted
            result = conn.execute(
                text("""
                WITH duplicate_contacts AS (
                    SELECT id, phone_number, tenant_id,
                           ROW_NUMBER() OVER (PARTITION BY tenant_id, phone_number ORDER BY created_at ASC) as rn
                    FROM contacts
                    WHERE deleted_at IS NULL
                    AND phone_number IS NOT NULL
                )
                UPDATE contacts
                SET deleted_at = NOW()
                WHERE id IN (
                    SELECT id FROM duplicate_contacts WHERE rn > 1
                )
                RETURNING id
            """)
            )

            deleted_count = result.rowcount
            logger.info(f"Deleted {deleted_count} duplicate contacts based on phone number")


def verify_cleanup():
    """Verify the cleanup results."""
    engine = get_engine()

    with engine.begin() as conn:
        # Count remaining active contacts
        result = conn.execute(
            text("""
            SELECT COUNT(*) FROM contacts WHERE deleted_at IS NULL
        """)
        )
        active_contacts = result.scalar()

        # Count active threads
        result = conn.execute(
            text("""
            SELECT COUNT(*) FROM chat_threads WHERE deleted_at IS NULL
        """)
        )
        active_threads = result.scalar()

        # Check for any remaining constraint violations
        result = conn.execute(
            text("""
            SELECT COUNT(*) as count, tenant_id, channel_instance_id, contact_id
            FROM chat_threads
            WHERE deleted_at IS NULL
            GROUP BY tenant_id, channel_instance_id, contact_id
            HAVING COUNT(*) > 1
        """)
        )

        violations = result.fetchall()

        logger.info("\n" + "=" * 60)
        logger.info("VERIFICATION RESULTS:")
        logger.info(f"  Active contacts: {active_contacts}")
        logger.info(f"  Active threads: {active_threads}")
        logger.info(f"  Constraint violations: {len(violations)}")

        if violations:
            logger.warning("  Still have constraint violations:")
            for count, tenant_id, channel_id, contact_id in violations:
                logger.warning(f"    {count} threads for contact {contact_id}")

        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        logger.info("Starting aggressive duplicate cleanup...")
        aggressive_cleanup()
        verify_cleanup()
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
