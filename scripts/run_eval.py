#!/usr/bin/env python3
"""
Main evaluation orchestrator.
- --dry-run: stub claude_client calls, no real subprocess
- --resume: skip completed items via JSONL checkpoint
- Runs both CricBench and BIRD, logs every detail
"""

import argparse
import datetime
import json
import logging
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Type
import time

# Local imports
import yaml
from prompt_builder import build_prompts
from cric_loader import load_cricbench
from bird_loader import load_bird_full, stratified_sample_bird, prepare_bird_instances
from claude_client import (
    call_claude,
    check_cli_auth as check_claude_auth,
    SessionLimitError as ClaudeSessionLimitError,
)
from codex_client import (
    call_codex,
    check_cli_auth as check_codex_auth,
    SessionLimitError as CodexSessionLimitError,
)
from local_client import (
    call_local,
    check_cli_auth as check_local_auth,
    SessionLimitError as LocalSessionLimitError,
)
from sql_extractor import clean_sql
from db_exec import execute_sql
from dma_eval import dma_match
from scorer import score_instance, aggregate_scores
from report import generate_report

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _seconds_until_reset(message: str, default: float = 300.0,
                         buffer: float = 30.0) -> float:
    m = re.search(r"reset[s]?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)", message, re.I)
    if not m:
        retry = re.search(r"retry_after=(\d+(?:\.\d+)?)s", message, re.I)
        if retry:
            try:
                return max(60.0, float(retry.group(1)) + buffer)
            except Exception:
                return default
        retry = re.search(r"retry after (\d+(?:\.\d+)?)s", message, re.I)
        if retry:
            try:
                return max(60.0, float(retry.group(1)) + buffer)
            except Exception:
                return default
        return default
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = m.group(3).lower()
    if ap == "pm" and hh != 12:
        hh += 12
    if ap == "am" and hh == 12:
        hh = 0
    now = datetime.datetime.now()
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    secs = (target - now).total_seconds() + buffer
    if secs <= 0 or secs > 6 * 3600:
        return default
    return max(60.0, secs)


def _record_key(record: dict):
    """Derive the identity key for a record (question_id for BIRD,
    base_question_id+language+variant_num for CricBench)."""
    if "question_id" in record:
        return record["question_id"]
    return (record.get("base_question_id"), record.get("language"), record.get("variant_num"))


def load_checkpoint(checkpoint_path: str) -> set:
    """Load completed item keys from JSONL checkpoint."""
    return {_record_key(r) for r in load_checkpoint_records(checkpoint_path)}


def load_checkpoint_records(checkpoint_path: str) -> List[dict]:
    """Load all records from a JSONL checkpoint, deduped by key (first occurrence wins)."""
    records = []
    seen = set()
    if Path(checkpoint_path).exists():
        with open(checkpoint_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        key = _record_key(record)
                        if key not in seen:
                            seen.add(key)
                            records.append(record)
                    except Exception:
                        pass
    return records


def append_checkpoint(checkpoint_path: str, record: dict) -> None:
    """Append record to JSONL checkpoint."""
    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "a") as f:
        f.write(json.dumps(record) + "\n")


# CricBench-shaped benchmarks: same loader (4-language variants, base_question_id
# clustering), same instance-key/record shape, just different db/gold/dk-prompt paths.
CRIC_FORMATS = {
    "cricbench": {"db_key": "cric_db", "gold_key": "cric_gold", "dk_key": "dk_prompt_cric"},
    "odi": {"db_key": "odi_db", "gold_key": "odi_gold", "dk_key": "dk_prompt_odi"},
    "t20i": {"db_key": "t20i_db", "gold_key": "t20i_gold", "dk_key": "dk_prompt_t20i"},
    "test": {"db_key": "test_db", "gold_key": "test_gold", "dk_key": "dk_prompt_test"},
}

CLIENT_IMPLS = {
    "claude": {
        "call": call_claude,
        "check": check_claude_auth,
        "limit_error": ClaudeSessionLimitError,
    },
    "codex": {
        "call": call_codex,
        "check": check_codex_auth,
        "limit_error": CodexSessionLimitError,
    },
    "local": {
        "call": call_local,
        "check": check_local_auth,
        "limit_error": LocalSessionLimitError,
    },
}


def get_gold_rows(db_path: str, gold_sql: str) -> Optional[List]:
    """Execute gold SQL to get expected result set."""
    gold_rows = execute_sql(db_path, gold_sql)
    if gold_rows is None:
        logger.warning(f"Gold SQL failed to execute: {gold_sql[:100]}")
        return None
    return gold_rows


def _get_client_impl(client_name: str) -> dict:
    if client_name not in CLIENT_IMPLS:
        raise ValueError(f"Unknown client: {client_name}")
    return CLIENT_IMPLS[client_name]


def evaluate_benchmark(
    benchmark: str,
    config: dict,
    dry_run: bool = False,
    resume: bool = False,
    limit: Optional[int] = None,
    domain_knowledge: bool = False,
    client: str = "claude",
    model_slug: Optional[str] = None,
) -> None:
    """
    Evaluate one benchmark (CricBench or BIRD).

    Args:
        benchmark: "cricbench" or "bird"
        config: Loaded config dict
        dry_run: If True, stub claude_client calls
        resume: If True, skip completed items from checkpoint
        limit: If set, stop after processing this many NEW instances this run
            (already-completed instances skipped via --resume don't count toward it)
    """
    logger.info(f"Starting {benchmark.upper()} evaluation")
    logger.info(f"  dry_run={dry_run}, resume={resume}, client={client}")

    client_impl = _get_client_impl(client)
    call_model = client_impl["call"]
    check_auth = client_impl["check"]
    limit_error = client_impl["limit_error"]
    if model_slug is None:
        if client == "claude":
            model_slug = config["model"]["slug"]
        elif client == "codex":
            model_slug = "gpt-5.4-mini"
        elif client == "local":
            raise ValueError(
                "--client local requires --model-slug (the exact model name your "
                "local server is serving, e.g. 'llama3.1:8b' for Ollama)"
            )

    # Setup paths
    outputs_dir = Path(config["paths"]["outputs"])
    outputs_dir.mkdir(parents=True, exist_ok=True)

    suffix = "_dk" if domain_knowledge else ""
    dk_prompt_path = None
    if domain_knowledge:
        dk_key = CRIC_FORMATS[benchmark]["dk_key"] if benchmark in CRIC_FORMATS else "dk_prompt_bird"
        dk_prompt_path = config["paths"].get(dk_key)
        if not dk_prompt_path:
            raise ValueError(f"--dk set but config paths.{dk_key} is not configured")
        if not Path(dk_prompt_path).exists():
            raise FileNotFoundError(f"DK prompt file not found: {dk_prompt_path}")
        logger.info(f"Domain-knowledge mode ON -> prompt: {dk_prompt_path}")

    if benchmark in CRIC_FORMATS:
        raw_checkpoint = outputs_dir / f"raw/{model_slug}_{benchmark}{suffix}.jsonl"
        records_file = outputs_dir / f"records/{model_slug}_{benchmark}{suffix}.json"
        db_path = config["paths"][CRIC_FORMATS[benchmark]["db_key"]]
        gold_path = config["paths"][CRIC_FORMATS[benchmark]["gold_key"]]

        # Load instances
        instances = load_cricbench(gold_path, db_path)
        logger.info(f"Loaded {len(instances)} {benchmark.upper()} instances")

    elif benchmark == "bird":
        raw_checkpoint = outputs_dir / f"raw/{model_slug}_bird{suffix}.jsonl"
        records_file = outputs_dir / f"records/{model_slug}_bird{suffix}.json"

        # Load and filter BIRD data
        dev_path = config["paths"]["bird_dev"]
        bird_databases_dir = config["paths"]["bird_databases"]

        full_questions = load_bird_full(dev_path, bird_databases_dir)
        sampled_questions, question_ids = stratified_sample_bird(
            full_questions,
            n_samples=config["bird"]["subset_size"],
            stratify_by=config["bird"]["stratify_by"],
            seed=config["bird"]["seed"],
        )

        # Save manifest
        manifest_path = outputs_dir / "manifest_bird_n400_seed42.json"
        with open(manifest_path, "w") as f:
            json.dump(question_ids, f, indent=2)
        logger.info(f"Saved BIRD manifest to {manifest_path}")

        # Prepare instances
        instances = prepare_bird_instances(sampled_questions, bird_databases_dir)
        logger.info(f"Prepared {len(instances)} BIRD instances")

    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")

    # Preflight: fail fast if the selected client can't reach the model, instead of
    # writing a whole run of "Model call failed" records (which --resume would
    # then skip). Skipped in dry-run since no real calls are made.
    if not dry_run:
        auth_err = check_auth(
            model_slug=model_slug,
            timeout_sec=config["timeouts"]["claude_subprocess_sec"],
        )
        if auth_err:
            low = auth_err.lower()
            if any(
                kw in low
                for kw in [
                    "session limit",
                    "usage limit",
                    "rate limit",
                    "quota",
                    "too many requests",
                ]
            ):
                # Transient: not an auth problem. The eval loop pauses/retries.
                logger.warning(
                    f"Session limit active at preflight ({auth_err}); "
                    "proceeding — the run will pause and retry until it resets."
                )
            else:
                if client == "claude":
                    hint = "Authenticate the CLI (run `claude` then /login, or set ANTHROPIC_API_KEY) and re-run."
                elif client == "codex":
                    hint = "Set OPENAI_API_KEY (and optional OPENAI_BASE_URL) and re-run."
                else:
                    hint = (
                        "Start your local inference server and confirm it's serving "
                        f"model '{model_slug}' at LOCAL_MODEL_BASE_URL "
                        "(default http://localhost:11434/v1, i.e. `ollama serve`)."
                    )
                raise RuntimeError(f"`{client}` is not usable: {auth_err}. {hint}")

    # Load checkpoint if resume enabled. Seed `records` with the already-completed
    # entries so the final records_file write doesn't drop them (previously, resumed
    # runs only wrote newly-processed instances, silently discarding prior progress).
    if resume:
        records = load_checkpoint_records(str(raw_checkpoint))
        completed_keys = {_record_key(r) for r in records}
    else:
        records = []
        completed_keys = set()
    logger.info(f"Resuming: {len(completed_keys)} already completed")

    # Evaluation loop
    errors = 0
    new_processed = 0

    for idx, instance in enumerate(instances):
        if limit is not None and new_processed >= limit:
            logger.info(f"Reached --limit {limit} new instances, stopping")
            break

        # Get instance key
        if benchmark in CRIC_FORMATS:
            instance_key = (instance["base_question_id"], instance["language"], instance.get("variant_num"))
        else:
            instance_key = instance["question_id"]

        # Skip if already completed (resume)
        if resume and instance_key in completed_keys:
            logger.debug(f"Skipping completed: {instance_key}")
            continue

        # Log progress
        if (idx + 1) % 10 == 0:
            logger.info(
                f"Progress: {idx + 1}/{len(instances)} "
                f"({errors} errors, {len(records)} scored)"
            )

        try:
            # Build prompts
            question = instance["question"]
            db_path = instance["db_path"]
            system_prompt, user_prompt = build_prompts(
                question, db_path, benchmark=benchmark, dk_prompt_path=dk_prompt_path
            )

            # Get gold result rows
            gold_rows = get_gold_rows(db_path, instance["gold_sql"])
            if gold_rows is None:
                gold_rows = []  # Treat failure as empty result
              
            if dry_run:
                raw_response = "SELECT 1"
                logger.debug("[DRY-RUN] Stubbed response")
            else:
                raw_response = None
                limit_waits = 0
                while True:
                    try:
                        raw_response = call_model(
                            user_prompt,
                            system_prompt,
                            model_slug=model_slug,
                            timeout_sec=config["timeouts"]["claude_subprocess_sec"],
                            max_retries=config["retry"]["max_attempts"],
                            backoff_factor=config["retry"]["backoff_factor"],
                        )
                        break
                    except limit_error as e:
                        limit_waits += 1
                        if limit_waits > 8:
                            logger.error(
                                f"Session limit still active after {limit_waits} "
                                f"waits; leaving {instance_key} for a later resume"
                            )
                            raw_response = None
                            break
                        wait_s = _seconds_until_reset(str(e))
                        logger.warning(
                            f"Pro session limit reached ({e}); pausing {wait_s:.0f}s "
                            f"(wait #{limit_waits}) then retrying the same instance"
                        )
                        time.sleep(wait_s)

            if raw_response is None:
                # Infrastructure failure (e.g. repeated timeout), NOT a wrong
                # answer. Do not record it — leaving it un-checkpointed means the
                # next --resume pass retries it.
                logger.warning(
                    f"No response for {instance_key}; will retry on a later resume"
                )
                errors += 1
                continue

            # Extract SQL
            extracted_sql = clean_sql(raw_response)

            # Execute predicted SQL
            pred_rows = execute_sql(
                db_path,
                extracted_sql,
                timeout_sec=config["timeouts"]["sql_execution_sec"],
            )

            # Score
            scores = score_instance(pred_rows, gold_rows)

            # Build record
            record = {
                **({"base_question_id": instance["base_question_id"], "language": instance["language"],
                    "variant_num": instance.get("variant_num")}
                   if benchmark in CRIC_FORMATS else {"question_id": instance["question_id"]}),
                "raw_response": raw_response[:500] if raw_response else None,  # Truncate for storage
                "extracted_sql": extracted_sql[:500] if extracted_sql else None,
                **scores,
                "timestamp": time.time(),
            }

            records.append(record)
            append_checkpoint(str(raw_checkpoint), record)
            new_processed += 1

            if (idx + 1) % 20 == 0:
                agg = aggregate_scores(records)
                logger.info(
                    f"  DMA accuracy so far: {agg['dma_accuracy']:.3f} "
                    f"({agg['dma_accuracy']*100:.1f}%)"
                )

        except Exception as e:
            logger.error(f"Exception processing {instance_key}: {e}")
            errors += 1

    # Aggregate and save records
    logger.info(f"Evaluation complete: {len(records)} scored, {errors} errors")
    agg = aggregate_scores(records)
    logger.info(f"Final {benchmark.upper()} DMA accuracy: {agg['dma_accuracy']:.3f}")

    records_file.parent.mkdir(parents=True, exist_ok=True)
    with open(records_file, "w") as f:
        json.dump(records, f, indent=2)
    logger.info(f"Records saved to {records_file}")

    # Auto-report only for the schema-only baseline condition. The DK condition
    # writes *_dk records; those are compared against the baseline separately
    # (compare_dk.py) rather than regenerating the baseline BIRD-vs-CricBench report.
    if (
        not domain_knowledge
        and benchmark == "cricbench"
        and client == "claude"
        and model_slug == config["model"]["slug"]
    ):
        cric_records = records_file.parent / f"{model_slug}_cricbench.json"
        bird_records = records_file.parent / f"{model_slug}_bird.json"
        if cric_records.exists() and bird_records.exists():
            logger.info("Both benchmarks complete, generating report...")
            generate_report(str(cric_records), str(bird_records), str(outputs_dir), model_name=model_slug)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CricBench + BIRD evaluation harness"
    )
    parser.add_argument(
        "--benchmark",
        choices=["bird", "cricbench", "odi", "t20i", "test"],
        required=True,
        help="Which benchmark to evaluate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stub model client calls (test only)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip completed items from checkpoint",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after processing this many NEW instances this run "
             "(instances skipped via --resume don't count toward it)",
    )
    parser.add_argument(
        "--dk",
        action="store_true",
        help="Use the domain-knowledge prompt (external cricket knowledge + "
             "schema) instead of the schema-only baseline. Writes to separate "
             "*_dk checkpoint/records files, preserving the baseline.",
    )
    parser.add_argument(
        "--client",
        choices=["claude", "codex", "local"],
        default="claude",
        help="Which model client to use",
    )
    parser.add_argument(
        "--model-slug",
        default=None,
        help="Model slug to send to the client (defaults by client)",
    )

    args = parser.parse_args()

    try:
        config = load_config(args.config)
        evaluate_benchmark(
            args.benchmark,
            config,
            dry_run=args.dry_run,
            resume=args.resume,
            limit=args.limit,
            domain_knowledge=args.dk,
            client=args.client,
            model_slug=args.model_slug,
        )
        logger.info("Evaluation succeeded")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
