def canon(rows):
    out = []
    for r in rows:
        if not isinstance(r, (list, tuple)): r = (r,)
        nr = []
        for v in r:
            if v is None: nr.append("__NULL__")
            elif isinstance(v, float): nr.append(round(v, 2))
            else: nr.append(v)
        out.append(tuple(nr))
    return sorted(out, key=lambda t: str(t))  # multiset, order-insensitive

def dma_match(gold_rows, pred_rows):
    if pred_rows is None:  # execution error / timeout
        return False
    return canon(gold_rows) == canon(pred_rows)