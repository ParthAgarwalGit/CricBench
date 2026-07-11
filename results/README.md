# results/

Example **raw model outputs** on the T20I split, kept for transparency and to
illustrate the format the evaluation harness consumes. Each record contains the
question, gold SQL/answer, and the model's `generated_sql` / `generated_answer`.

- `t20i_deepseek_v3.json` — DeepSeek V3 on T20I
- `t20i_deepseek_r1.json` — DeepSeek R1 on T20I

Score them with:

```bash
python scripts/evaluate.py --db t20i.db --queries results/t20i_deepseek_r1.json --pred-key generated_sql
```

These are a representative sample; the complete set of model outputs across all
formats and models is available from the authors on request.
