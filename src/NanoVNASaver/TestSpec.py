"""Test spec parsing and evaluation helpers.

This module defines TestPoint and TestSpec dataclasses and provides helpers
for loading a JSON test spec and evaluating it against sweep data.

JSON template example:
{
  "sweep": { "start": 700000000, "stop": 6000000000, "points": 201, "segments": 30 },
  "tests": [
    {
      "name": "900MHz S21",
      "parameter": "S21",
      "frequency": 900000000,
      "span": 3000000,
      "limit_db": -30.0,
      "direction": "under"
    }
  ],
  "meta": { "id": "test1", "author": "JL" }
}
"""
from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Optional

from .RFTools import Datapoint


DEFAULT_TEST_SPEC_PATH = Path("test_spec.json")


@dataclass
class TestPoint:
    name: str
    parameter: str
    frequency: int
    span: int
    limit_db: float
    direction: str

@dataclass
class TestResult:
    """Result of evaluating a single TestPoint.

    Stores the original TestPoint and the computed min/max/gating info.
    """
    tp: TestPoint
    passed: bool
    min: Optional[float]
    max: Optional[float]
    failing: List[int]
    samples: int

@dataclass
class TestData:
    serial: str
    id: str
    meta: str
    passed: bool
    pcb_lot: str
    results: List[TestResult]

@dataclass
class TestSpec:
    sweep: dict
    tests: List[TestPoint]


def parse_test_spec(path: Optional[str] = None) -> Optional[TestSpec]:
    """Load a JSON test spec from path (or default). Returns None if no file."""
    p = Path(path) if path else DEFAULT_TEST_SPEC_PATH
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    tests: List[TestPoint] = []
    for t in data.get("tests", []):
        tests.append(
            TestPoint(
                name=t.get("name", ""),
                parameter=t["parameter"],
                frequency=int(t["frequency"]),
                span=int(t.get("span", 0)),
                limit_db=float(t["limit_db"]),
                direction=t.get("direction", "over"),
            )
        )
    return TestSpec(sweep=data.get("sweep", {}), tests=tests)


def evaluate_test_point(data: List[Datapoint], tp: TestPoint) -> dict:
    """Evaluate a single TestPoint against a list of Datapoint objects.

    Returns a result dict containing pass (bool), min/max, failing sample freqs, sample count.
    """
    low = tp.frequency - tp.span // 2
    high = tp.frequency + tp.span // 2
    samples = [dp for dp in data if low <= dp.freq <= high]
    if not samples:
        return {
            "name": tp.name,
            "pass": False,
            "reason": "no_samples",
            "samples": [],
            "min": None,
            "max": None,
            "failing": [],
        }
    gains = [dp.gain for dp in samples]
    min_g = min(gains)
    max_g = max(gains)
    if tp.direction == "over":
        failing = [dp for dp in samples if dp.gain < tp.limit_db]
        passed = len(failing) == 0
    else:
        failing = [dp for dp in samples if dp.gain > tp.limit_db]
        passed = len(failing) == 0
    return {
        "name": tp.name,
        "pass": passed,
        "min": min_g,
        "max": max_g,
        "failing": [dp.freq for dp in failing],
        "samples": len(samples),
    }


def evaluate_testspec(s11: List[Datapoint], s21: List[Datapoint], spec: TestSpec) -> List[dict]:
    results = []
    for tp in spec.tests:
        data = s11 if tp.parameter.lower() == "s11" else s21
        res = evaluate_test_point(data, tp)
        res.update(
            {
                "parameter": tp.parameter,
                "freq": tp.frequency,
                "limit_db": tp.limit_db,
                "direction": tp.direction,
            }
        )
        results.append(res)
    return results
