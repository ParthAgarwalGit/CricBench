# data/

The CricBench gold datasets — natural-language questions (English + native-script,
code-mixed Hindi/Punjabi/Telugu) paired with hand-authored, validated gold SQL.

| File | Format | Base questions | `db_id` |
|------|--------|:--------------:|---------|
| `test.json` | Test cricket | 169 | `tests` |
| `odi.json`  | ODI          | 100  | `wc_db` |
| `t20i.json` | T20 International | 200 | `t20i.db` |
| `ipl.json`  | Indian Premier League | 200 | `ipl_db` |

See the top-level [README](../README.md#json-format) for the record schema and the
join-based complexity distribution. Databases are built from
[Cricsheet](https://cricsheet.org) via [`scripts/ingest.py`](../scripts/ingest.py)
using the DDL in [`schemas/`](../schemas).
