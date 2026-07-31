import pytest

from intelligence.walk_forward import purged_walk_forward_splits, validate_fold


def test_expanding_splits_are_chronological_and_embargoed():
    folds = purged_walk_forward_splits(range(20), train_size=8, test_size=3, embargo_rows=2)
    assert len(folds) == 3
    assert [(f.train_start, f.train_end, f.test_start, f.test_end) for f in folds] == [
        (0, 8, 10, 13), (0, 11, 13, 16), (0, 14, 16, 19),
    ]
    for fold in folds:
        validate_fold(fold)


def test_rolling_window_does_not_reuse_future_rows():
    folds = purged_walk_forward_splits(range(18), train_size=6, test_size=2,
                                       embargo_rows=1, expanding=False)
    assert all(f.train_end < f.test_start for f in folds)
    assert all(f.train_end - f.train_start == 6 for f in folds)


@pytest.mark.parametrize("timestamps", [[1, 2, 2, 3], [1, 3, 2, 4]])
def test_duplicate_or_unsorted_timestamps_are_rejected(timestamps):
    with pytest.raises(ValueError):
        purged_walk_forward_splits(timestamps, train_size=2, test_size=1)


def test_embargo_cannot_be_disabled():
    with pytest.raises(ValueError):
        purged_walk_forward_splits(range(10), train_size=5, test_size=2, embargo_rows=0)
