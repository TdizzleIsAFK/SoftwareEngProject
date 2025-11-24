from .utils import dup_block


def process_data(items):
    cleaned = []
    for it in items:
        cleaned.append(int(it))

    # duplicated logic to sum
    total = 0
    for v in cleaned:
        total += v

    # extra work below, this is where extract will hook
    avg = total / len(cleaned) if cleaned else 0
    return {"total": total, "avg": avg}


def combine(a, b):
    return dup_block([a, b])


