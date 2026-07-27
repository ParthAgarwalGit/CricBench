import json
import numpy as np

def load_results(path):
    """
    Load scored records from a file. Accepts either a JSON array of
    objects or newline-delimited JSON (JSONL). Returns a list of dicts.
    """
    with open(path) as f:
        content = f.read().strip()
    if not content:
        return []
    try:
        data = json.loads(content)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        records = []
        for line in content.splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records


def format_pct(x, decimals=2):
    """Format a proportion (0-1) as a percentage string, e.g. 0.7345 -> '73.45%'."""
    return f"{100 * x:.{decimals}f}%"


def _cluster_sums(records, metric_key, cluster_key):
    """
    Group records into clusters and return (sums, counts) arrays, one
    entry per cluster: sums[i] = sum of metric_key over cluster i,
    counts[i] = number of items in cluster i.
    If cluster_key is None, every record is treated as its own singleton
    cluster (plain item-level bootstrap).
    """
    clusters = {}
    for i, r in enumerate(records):
        cid = r[cluster_key] if cluster_key is not None else i
        val = float(r[metric_key])
        s, n = clusters.get(cid, (0.0, 0))
        clusters[cid] = (s + val, n + 1)
    sums = np.array([v[0] for v in clusters.values()], dtype=np.float64)
    counts = np.array([v[1] for v in clusters.values()], dtype=np.int64)
    return sums, counts


def bootstrap_metric(records, metric_key="dma_correct", cluster_key=None,
                      n_resamples=10000, seed=42, alpha=0.05):
    """
    95% clustered bootstrap CI for the mean of `metric_key` over `records`.
    Resamples clusters (not individual items) with replacement; all items
    in a resampled cluster are pooled to compute each resample's mean.
    Vectorized, numpy-only.

    Returns:
        {"point_estimate", "ci_low", "ci_high", "n_items", "n_clusters",
         "n_resamples", "seed"}
    """
    if not records:
        raise ValueError("bootstrap_metric: no records provided")

    sums, counts = _cluster_sums(records, metric_key, cluster_key)
    n_clusters = len(sums)
    point_estimate = sums.sum() / counts.sum()

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_clusters, size=(n_resamples, n_clusters))
    resample_sums = sums[idx].sum(axis=1)
    resample_counts = counts[idx].sum(axis=1)
    resample_means = resample_sums / resample_counts

    lo = np.percentile(resample_means, 100 * (alpha / 2))
    hi = np.percentile(resample_means, 100 * (1 - alpha / 2))

    return {
        "point_estimate": float(point_estimate),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "n_items": int(counts.sum()),
        "n_clusters": int(n_clusters),
        "n_resamples": n_resamples,
        "seed": seed,
    }


def bootstrap_gap(records_a, records_b, metric_key="dma_correct",
                   cluster_key_a=None, cluster_key_b=None,
                   n_resamples=10000, seed=42, alpha=0.05):
    """
    95% CI on gap = mean(metric_key over records_a) - mean(metric_key over
    records_b). The two benchmarks are resampled independently (separate 
    cluster sets, both draws come from the same seeded generator so the whole
    call is reproducible) and the gap is computed per resample.

    Returns:
        {"point_estimate", "ci_low", "ci_high", "excludes_zero",
         "n_resamples", "seed"}
    """
    if not records_a or not records_b:
        raise ValueError("bootstrap_gap: both record sets must be non-empty")

    sums_a, counts_a = _cluster_sums(records_a, metric_key, cluster_key_a)
    sums_b, counts_b = _cluster_sums(records_b, metric_key, cluster_key_b)

    point_a = sums_a.sum() / counts_a.sum()
    point_b = sums_b.sum() / counts_b.sum()
    point_gap = float(point_a - point_b)

    rng = np.random.default_rng(seed)
    idx_a = rng.integers(0, len(sums_a), size=(n_resamples, len(sums_a)))
    idx_b = rng.integers(0, len(sums_b), size=(n_resamples, len(sums_b)))

    means_a = sums_a[idx_a].sum(axis=1) / counts_a[idx_a].sum(axis=1)
    means_b = sums_b[idx_b].sum(axis=1) / counts_b[idx_b].sum(axis=1)
    gaps = means_a - means_b

    lo = np.percentile(gaps, 100 * (alpha / 2))
    hi = np.percentile(gaps, 100 * (1 - alpha / 2))
    excludes_zero = bool(lo > 0 or hi < 0)

    return {
        "point_estimate": point_gap,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "excludes_zero": excludes_zero,
        "n_resamples": n_resamples,
        "seed": seed,
    }
