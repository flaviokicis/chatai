#!/usr/bin/env python
"""
Final cleanup script that properly handles all duplicates.
This version deletes duplicate threads first, then contacts.
"""

import logging

from sqlalchemy import text

from app.db.session import get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def final_cleanup():
    """Final cleanup of all duplicates."""

    engine = get_engine()

    # Use separate transactions for each step
    logger.info("Starting final cleanup of duplicates...")

    # Step 1: Identify duplicate contacts
    logger.info("\nStep 1: Identifying duplicate contacts...")
    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT id, tenant_id, external_id, created_at
            FROM contacts
            WHERE deleted_at IS NULL
            ORDER BY tenant_id, created_at ASC
        """)
        )

        all_contacts = result.fetchall()
        logger.info(f"Found {len(all_contacts)} active contacts")

    # Decrypt and group contacts
    from app.db.types import _get_fernet

    fernet = _get_fernet()

    contact_groups = {}
    for contact_id, tenant_id, encrypted_ext_id, created_at in all_contacts:
        try:
            ext_id = fernet.decrypt(bytes(encrypted_ext_id)).decode("utf-8")
            key = (tenant_id, ext_id)
            if key not in contact_groups:
                contact_groups[key] = []
            contact_groups[key].append({"id": contact_id, "created_at": created_at})
        except Exception as e:
            logger.warning(f"Could not decrypt contact {contact_id}: {e}")

    # Find duplicates
    duplicates = {k: v for k, v in contact_groups.items() if len(v) > 1}
    logger.info(f"Found {len(duplicates)} groups with duplicates")

    if not duplicates:
        logger.info("No duplicates found!")
        return

    # Step 2: For each duplicate group, keep oldest and delete others
    for (tenant_id, ext_id), contacts in duplicates.items():
        logger.info(f"\nProcessing duplicates for {ext_id[:40]}...")

        # Sort by creation date
        contacts.sort(key=lambda c: c["created_at"])
        keeper = contacts[0]
        to_delete = contacts[1:]

        logger.info(f"  Keeper: {keeper['id']}")
        logger.info(f"  To delete: {len(to_delete)} contacts")

        keeper_id = keeper["id"]
        delete_ids = [c["id"] for c in to_delete]

        # Step 3: Delete all threads for duplicate contacts
        with engine.begin() as conn:
            for contact_id in delete_ids:
                # First, get all threads for this contact
                result = conn.execute(
                    text("""
                    SELECT id, channel_instance_id 
                    FROM chat_threads 
                    WHERE contact_id = :contact_id 
                    AND deleted_at IS NULL
                """),
                    {"contact_id": contact_id},
                )

                threads = result.fetchall()

                for thread_id, channel_id in threads:
                    # Check if keeper has a thread for this channel
                    keeper_thread = conn.execute(
                        text("""
                        SELECT id FROM chat_threads
                        WHERE tenant_id = :tenant_id
                        AND channel_instance_id = :channel_id
                        AND contact_id = :keeper_id
                        AND deleted_at IS NULL
                    """),
                        {"tenant_id": tenant_id, "channel_id": channel_id, "keeper_id": keeper_id},
                    ).fetchone()

                    if keeper_thread:
                        # Keeper has a thread, delete the duplicate
                        logger.info(f"    Deleting duplicate thread {thread_id}")

                        # First delete all messages in this thread
                        conn.execute(
                            text("""
                            DELETE FROM messages WHERE thread_id = :thread_id
                        """),
                            {"thread_id": thread_id},
                        )

                        # Then delete the thread
                        conn.execute(
                            text("""
                            DELETE FROM chat_threads WHERE id = :thread_id
                        """),
                            {"thread_id": thread_id},
                        )
                    else:
                        # Keeper doesn't have this thread, transfer it
                        logger.info(f"    Transferring thread {thread_id} to keeper")

                        # Update thread to point to keeper
                        conn.execute(
                            text("""
                            UPDATE chat_threads 
                            SET contact_id = :keeper_id 
                            WHERE id = :thread_id
                        """),
                            {"keeper_id": keeper_id, "thread_id": thread_id},
                        )

                        # Update messages too
                        conn.execute(
                            text("""
                            UPDATE messages 
                            SET contact_id = :keeper_id 
                            WHERE thread_id = :thread_id
                        """),
                            {"keeper_id": keeper_id, "thread_id": thread_id},
                        )

                # Now delete the duplicate contact
                conn.execute(
                    text("""
                    DELETE FROM contacts WHERE id = :contact_id
                """),
                    {"contact_id": contact_id},
                )

                logger.info(f"  Deleted contact {contact_id}")

    logger.info("\n" + "=" * 60)
    logger.info("CLEANUP COMPLETED!")
    logger.info("=" * 60)


def verify_results():
    """Verify the cleanup worked."""
    engine = get_engine()

    with engine.connect() as conn:
        # Count active contacts
        result = conn.execute(text("SELECT COUNT(*) FROM contacts WHERE deleted_at IS NULL"))
        contact_count = result.scalar()

        # Count active threads
        result = conn.execute(text("SELECT COUNT(*) FROM chat_threads WHERE deleted_at IS NULL"))
        thread_count = result.scalar()

        # Check for constraint violations
        result = conn.execute(
            text("""
            SELECT COUNT(*) as cnt, tenant_id, channel_instance_id, contact_id
            FROM chat_threads
            WHERE deleted_at IS NULL
            GROUP BY tenant_id, channel_instance_id, contact_id
            HAVING COUNT(*) > 1
        """)
        )
        violations = result.fetchall()

        logger.info("\nVERIFICATION:")
        logger.info(f"  Active contacts: {contact_count}")
        logger.info(f"  Active threads: {thread_count}")
        logger.info(f"  Constraint violations: {len(violations)}")

        # Check for duplicate contacts
        result = conn.execute(
            text("""
            SELECT id, external_id FROM contacts WHERE deleted_at IS NULL
        """)
        )
        contacts = result.fetchall()

        # Decrypt and check for duplicates
        from app.db.types import _get_fernet

        fernet = _get_fernet()

        seen = set()
        dups = []
        for contact_id, encrypted_ext_id in contacts:
            try:
                ext_id = fernet.decrypt(bytes(encrypted_ext_id)).decode("utf-8")
                if ext_id in seen:
                    dups.append(ext_id)
                seen.add(ext_id)
            except:
                pass

        logger.info(f"  Duplicate external_ids: {len(dups)}")
        if dups:
            for dup in dups[:5]:
                logger.warning(f"    Still duplicate: {dup}")


if __name__ == "__main__":
    try:
        final_cleanup()
        verify_results()
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
