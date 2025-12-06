from .utils import dup_block


def process_data(items):
    cleaned = []
    for it in items:
        cleaned.append(int(it))
    total = compute_total(cleaned)

    # extra work below, this is where extract will hook
    avg = total / len(cleaned) if cleaned else 0
    return {"total": total, "avg": avg}
def compute_total(cleaned):

    # duplicated logic to sum
    total = 0
    for v in cleaned:
        total += v
    return total


def combine(a, b):
    return dup_block([a, b])


