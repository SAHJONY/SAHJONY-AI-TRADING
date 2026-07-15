"""Purged chronological walk-forward splits with explicit leakage controls."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Sequence


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    embargo_rows: int

    def to_dict(self) -> dict:
        return asdict(self)


def purged_walk_forward_splits(
    timestamps: Sequence[datetime | str | int | float], *,
    train_size: int, test_size: int, embargo_rows: int = 1,
    expanding: bool = True,
) -> list[WalkForwardFold]:
    """Return ordered train/test index bounds with a mandatory embargo.

    Bounds use Python slice semantics (end-exclusive). Input timestamps must be
    strictly increasing, preventing shuffled or duplicate observations from
    silently entering time-series evaluation.
    """
    if train_size < 2 or test_size < 1 or embargo_rows < 1:
        raise ValueError("train_size>=2, test_size>=1, and embargo_rows>=1 are required")
    if len(timestamps) < train_size + embargo_rows + test_size:
        raise ValueError("insufficient observations for one purged walk-forward fold")
    normalized = [str(item) if isinstance(item, datetime) else item for item in timestamps]
    if any(normalized[i] >= normalized[i + 1] for i in range(len(normalized) - 1)):
        raise ValueError("timestamps must be unique and strictly increasing")

    folds: list[WalkForwardFold] = []
    train_end = train_size
    while train_end + embargo_rows + test_size <= len(timestamps):
        test_start = train_end + embargo_rows
        train_start = 0 if expanding else train_end - train_size
        folds.append(WalkForwardFold(
            fold=len(folds) + 1, train_start=train_start, train_end=train_end,
            test_start=test_start, test_end=test_start + test_size,
            embargo_rows=embargo_rows,
        ))
        train_end += test_size
    return folds


def validate_fold(fold: WalkForwardFold) -> None:
    if fold.train_start < 0 or fold.train_end <= fold.train_start:
        raise ValueError("invalid training range")
    if fold.test_start - fold.train_end < fold.embargo_rows:
        raise ValueError("train/test embargo is violated")
    if fold.test_end <= fold.test_start:
        raise ValueError("invalid test range")
