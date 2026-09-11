#!/usr/bin/env python3
"""
backfill_embeddings.py — Generates Gemini Embedding 2 (768-dim) vectors for
all existing events that don't yet have an embedding stored in the database.

Usage:
    python scripts/backfill_embeddings.py           # skip already-embedded events
    python scripts/backfill_embeddings.py --force   # regenerate all embeddings

Respects free-tier limits: 100 RPM, 30,000 TPM, 1,000 RPD.
"""

import sys
import time
import argparse
import logging
import os

# Allow running from the concert_backend directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.supabase_client import supabase_admin
from app.services.embedding_service import generate_event_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_embeddings")

# Safety pacing: max ~60 RPM (well under 100 RPM limit)
REQUESTS_PER_MINUTE = 60
DELAY_BETWEEN_REQUESTS = 60.0 / REQUESTS_PER_MINUTE  # ~1 second between requests
MAX_RETRIES = 3
RETRY_WAIT = 5  # seconds to wait before retry

def main():
    parser = argparse.ArgumentParser(description="Backfill event embeddings")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate embeddings for ALL events, even those already embedded")
    args = parser.parse_args()

    logger.info("Fetching all events from Supabase...")
    result = supabase_admin.table("events").select(
        "event_id, artist_name, venue_name, city, event_type, description, event_date, event_time, embedding"
    ).execute()

    all_events = result.data or []
    total = len(all_events)
    logger.info(f"Total events: {total}")

    if args.force:
        to_process = all_events
        already_embedded = 0
    else:
        to_process = [e for e in all_events if not e.get("embedding")]
        already_embedded = total - len(to_process)

    logger.info(f"Already embedded: {already_embedded}")
    logger.info(f"To process: {len(to_process)}")

    success_count = 0
    fail_count = 0

    for i, event in enumerate(to_process):
        event_id = event["event_id"]
        logger.info(f"[{i+1}/{len(to_process)}] Embedding event {event_id} — {event.get('artist_name', '?')}")

        vector = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                vector = generate_event_embedding(event)
                if vector:
                    break
                else:
                    logger.warning(f"  Attempt {attempt}: generate_event_embedding returned None")
            except Exception as exc:
                logger.warning(f"  Attempt {attempt}: Error — {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_WAIT)

        if vector:
            try:
                supabase_admin.table("events") \
                    .update({"embedding": vector}) \
                    .eq("event_id", event_id) \
                    .execute()
                logger.info(f"  ✓ Stored embedding ({len(vector)} dims)")
                success_count += 1
            except Exception as exc:
                logger.error(f"  ✗ Failed to store embedding: {exc}")
                fail_count += 1
        else:
            logger.error(f"  ✗ Could not generate embedding after {MAX_RETRIES} attempts")
            fail_count += 1

        # Pace requests to respect free-tier limits
        if i < len(to_process) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print("\n" + "="*50)
    print("BACKFILL SUMMARY")
    print(f"  Total events:      {total}")
    print(f"  Already embedded:  {already_embedded}")
    print(f"  Successfully embedded: {success_count}")
    print(f"  Failed:            {fail_count}")
    print("="*50)

if __name__ == "__main__":
    main()
