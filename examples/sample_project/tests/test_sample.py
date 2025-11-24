from sample.main import process_data, combine


def test_process_data_total_and_avg():
    result = process_data([1, 2, 3])
    assert result["total"] == 6
    assert result["avg"] == 2


def test_combine_uses_dup_block():
    assert combine(4, 5) == 9


