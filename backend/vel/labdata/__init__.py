"""Measured tables transcribed from real lab reports, importable as measurement sets.

Each value is what the report says, in the report's unit; an interpretation that changes a
value (phase → line, a missing unit) is stated in the table's or the row's note and never made
silently. Validation that every table fits its experiment's measurement definition is in
tests/test_labdata.py.
"""

from vel.labdata.datasets import DATASETS, Dataset, DTable, by_experiment, get

__all__ = ["DATASETS", "DTable", "Dataset", "by_experiment", "get"]
