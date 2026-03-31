"""
verify_queries_sqlite.py
Runs every SQL query from the dataset against an SQLite database using a timeout,
and checks results against the answer key.
"""
import json
import re
import decimal
import datetime
import sqlite3
import threading
import queue
from pathlib import Path

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DB_PATH = Path("data/processed/t20_I.db")
DATASET_FILE = "_cricbench.json"
OUTPUT_FILE = "verification_tests_results.json"

# ─── JSON serializer that handles Decimal / date ────────────────────────────
class SafeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal): 
            return float(o)
        if isinstance(o, (datetime.date, datetime.datetime)): 
            return str(o)
        return super().default(o)

# ─── SQLite Execution with Timeout ───────────────────────────────────────────
def run_sql_with_timeout_sqlite(db_path: Path, sql: str, timeout_sec: int = 20):
    q = queue.Queue()

    def _target():
        try:
            # Setting timeout for the connection to avoid locking issues
            conn = sqlite3.connect(str(db_path), timeout=5)
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in (cur.description or [])]
            conn.close()
            q.put((rows, cols, None))
        except Exception as e:
            q.put((None, [], str(e)))

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_sec)
    
    if t.is_alive():
        return None, [], "TIMEOUT"
    return q.get()

# ─── Answer matching ─────────────────────────────────────────────────────────
def extract_numbers(text):
    return set(re.findall(r'\b\d+(?:\.\d+)?\b', str(text)))

def extract_words(text):
    stop = {'the','and','for','with','from','that','this','has','was','are','not',
            'all','any','each','per','out','off','in','at','vs','by','of'}
    return {w for w in re.findall(r'[a-zA-Z]{3,}', str(text).lower()) if w not in stop}

def rows_to_text(rows):
    if not rows:
        return ""
    return ' | '.join(str(c).lower().strip() for row in rows for c in row)

def answers_match(db_rows, answer_list):
    if not db_rows:
        return False, 0.0, "empty result"
        
    db_text = rows_to_text(db_rows)
    db_nums = extract_numbers(db_text)
    db_words = extract_words(db_text)
    
    # Flatten the answer list safely to strings
    combined = ' '.join(str(x) for x in answer_list)
    ans_nums = extract_numbers(combined)
    ans_words = extract_words(combined)
    
    total = len(ans_nums) + len(ans_words)
    if total == 0:
        return True, 1.0, "no tokens to match against"
        
    hits = len(ans_nums & db_nums) + len(ans_words & db_words)
    score = hits / total
    detail = f"nums {len(ans_nums & db_nums)}/{len(ans_nums)}  words {len(ans_words & db_words)}/{len(ans_words)}"
    
    return score >= 0.98, round(score, 3), detail

# ─── Main ────────────────────────────────────────────────────────────────────
def run():
    if not DB_PATH.exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return

    try:
        with open(DATASET_FILE, encoding='utf-8') as f:
            dataset = json.load(f)
    except FileNotFoundError:
        print(f"Error: Dataset file not found at {DATASET_FILE}")
        return

    print(f"Connected to SQLite DB: '{DB_PATH}'\n")

    total = sql_ok = sql_err = matched = mismatched = skipped = timeouts = 0
    log = []

    for idx, item in enumerate(dataset, 1):
        q = item.get('question', '')
        # Handle both 'query' and 'sql_query' keys used in your JSON
        sql = item.get('sql_query') or item.get('query', '')
        sql = sql.strip()
        ans = item.get('answer', [])

        if not sql:
            print(f"[{idx:>3}] SKIP  — {q[:70]}")
            log.append({'idx': idx, 'status': 'SKIP', 'question': q, 'answer': ans})
            skipped += 1
            continue

        total += 1
        
        # Execute query
        rows, cols, err = run_sql_with_timeout_sqlite(DB_PATH, sql)

        if err == "TIMEOUT":
            timeouts += 1
            print(f"[{idx:>3}] ⏳ TIMEOUT — {q[:60]}")
            log.append({'idx': idx, 'status': 'TIMEOUT', 'question': q, 'sql': sql, 'answer': ans})
            continue
            
        if err:
            sql_err += 1
            print(f"[{idx:>3}] ❌ ERROR — {q[:60]}")
            print(f"       {err}")
            log.append({'idx': idx, 'status': 'SQL_ERROR', 'question': q,
                        'sql': sql, 'error': err, 'answer': ans})
            continue

        # If we reach here, SQL executed successfully
        sql_ok += 1
        ok, score, detail = answers_match(rows, ans)
        
        if ok:
            matched += 1
            print(f"[{idx:>3}] ✅ MATCH  (score {score}) — {q[:60]}")
        else:
            mismatched += 1
            print(f"[{idx:>3}] ⚠️  MISMATCH (score {score}) — {q[:60]}")
            print(f"       {detail}")
            print(f"       Expected: {ans[:2]}")
            print(f"       Got:      {rows[:2]}")
            
        log.append({
            'idx': idx, 
            'status': 'MATCH' if ok else 'MISMATCH',
            'score': score, 
            'question': q, 
            'sql': sql,
            'db_rows': [[str(c) for c in r] for r in (rows[:5] if rows else [])],
            'answer': ans
        })

    print(f"\n{'='*60}")
    print(f"  Total queries run   : {total}")
    if total:
        print(f"  ✅  Executed OK     : {sql_ok}  ({sql_ok/total*100:.1f}%)")
    print(f"  ❌  SQL errors      : {sql_err}")
    print(f"  ⏳  Timeouts        : {timeouts}")
    if sql_ok:
        print(f"  ✅  Answer matched  : {matched}  ({matched/sql_ok*100:.1f}% of executed)")
    print(f"  ⚠️   Answer mismatch : {mismatched}")
    print(f"  ⏭️   Skipped         : {skipped}")
    print(f"{'='*60}")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=2, ensure_ascii=False, cls=SafeEncoder)
    print(f"Results → {OUTPUT_FILE}")

if __name__ == "__main__":
    run()