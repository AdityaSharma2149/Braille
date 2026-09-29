import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmark import benchmark_braille, benchmark_ocr, benchmark_spatial_comprehension


def test_benchmark_ocr_produces_bounded_percentage():
    result = benchmark_ocr()
    assert 0 <= result["average_accuracy_pct"] <= 100
    assert result["sample_count"] == len(result["per_sample"])


def test_benchmark_braille_produces_bounded_percentage():
    result = benchmark_braille()
    assert 0 <= result["aggregate_accuracy_pct"] <= 100
    assert result["sample_count"] == len(result["per_sample"])


def test_benchmark_spatial_comprehension_is_bounded_and_nonnegative_reduction():
    result = benchmark_spatial_comprehension()
    assert 0 <= result["naive_ambiguous_pct"] <= 100
    assert 0 <= result["structured_ambiguous_pct"] <= 100
    assert result["ambiguity_reduction_pct"] >= 0
    # By construction, engine.speak() output is never structurally ambiguous.
    assert result["structured_ambiguous_pct"] == 0
