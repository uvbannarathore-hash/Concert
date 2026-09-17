#!/usr/bin/env python3
"""
backfill_embeddings.py — Generates Gemini Embedding 2 (768-dim) vectors for
all existing events that don't yet have an embedding stored in the database.

Usage:
    python scripts/backfill_embeddings.py           # skip already-embedded events
    python scripts/backfill_embeddings.py --force   # regenerate all embeddings
    python scripts/backfill_embeddings.py --batch-size 50

Respects free-tier limits by batching requests (up to 100 per call).
"""

import sys
import time
import argparse
import logging
import os
import random

# Allow running from the concert_backend directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.supabase_client import supabase_admin
from app.services.embedding_service import generate_event_embeddings_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_embeddings")

# Safety pacing
DELAY_BETWEEN_BATCHES = 1.0  # seconds between batch requests
MAX_RETRIES = 3

def chunk_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def process_batch(batch_events, attempt=1):
    """Process a batch of events with exponential backoff."""
    batch_size = len(batch_events)
    try:
        vectors = generate_event_embeddings_batch(batch_events)
        if vectors is None or len(vectors) != batch_size:
            raise ValueError(f"generate_event_embeddings_batch returned invalid length (expected {batch_size})")
        return vectors
    except Exception as exc:
        logger.warning(f"Batch generation error (Attempt {attempt}/{MAX_RETRIES}): {exc}")
        if attempt < MAX_RETRIES:
            # Exponential backoff: 2^attempt + jitter
            sleep_time = (2 ** attempt) + random.uniform(0, 1)
            logger.info(f"Retrying batch in {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
            return process_batch(batch_events, attempt + 1)
        else:
            logger.error(f"Batch generation failed after {MAX_RETRIES} attempts.")
            return None

def main():
    default_batch = int(os.environ.get("EMBEDDING_BATCH_SIZE", "100"))
    
    parser = argparse.ArgumentParser(description="Backfill event embeddings")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate embeddings for ALL events, even those already embedded")
    parser.add_argument("--batch-size", type=int, default=default_batch,
                        help=f"Number of events to process per API call (default: {default_batch})")
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
    
    if not to_process:
        logger.info("Nothing to process.")
        return

    success_count = 0
    fail_count = 0
    failed_event_ids = []

    batches = list(chunk_list(to_process, args.batch_size))
    
    for i, batch in enumerate(batches):
        logger.info(f"Processing Batch {i+1}/{len(batches)} (Size: {len(batch)})...")
        
        vectors = process_batch(batch)
        
        if not vectors:
            # Entire batch failed to generate
            fail_count += len(batch)
            failed_event_ids.extend([e["event_id"] for e in batch])
            continue
            
        # Update DB for each successfully generated vector in the batch
        for j, event in enumerate(batch):
            event_id = event["event_id"]
            vector = vectors[j]
            
            if vector is None:
                logger.error(f"  ✗ Event {event_id}: Model returned None for embedding")
                fail_count += 1
                failed_event_ids.append(event_id)
                continue
                
            try:
                supabase_admin.table("events") \
                    .update({"embedding": vector}) \
                    .eq("event_id", event_id) \
                    .execute()
                success_count += 1
            except Exception as exc:
                logger.error(f"  ✗ Failed to store embedding for {event_id}: {exc}")
                fail_count += 1
                failed_event_ids.append(event_id)

        if i < len(batches) - 1:
            time.sleep(DELAY_BETWEEN_BATCHES)

    logger.info("--- Backfill Complete ---")
    logger.info(f"Successfully updated: {success_count}")
    logger.info(f"Failed to update: {fail_count}")
    if failed_event_ids:
        logger.warning(f"Failed Event IDs: {failed_event_ids}")

if __name__ == "__main__":
    main()
