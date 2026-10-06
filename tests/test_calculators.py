from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

import pytest

from osu_native_py.native import attributes
from osu_native_py.wrapper.calculators import create_difficulty_calculator
from osu_native_py.wrapper.calculators import create_performance_calculator
from osu_native_py.wrapper.objects import Beatmap
from osu_native_py.wrapper.objects import Mod
from osu_native_py.wrapper.objects import ModsCollection
from osu_native_py.wrapper.objects import Ruleset
from osu_native_py.wrapper.objects import ScoreInfo

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "osu-native/osu.Native.Tests/Resources"
CASES = json.loads((ROOT / "build/generated/test-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda case: f"{case['attributes']}-{Path(case['beatmap']).stem}-{case['mods'] or 'NM'}",
)
def test_calculator(case):
    with ExitStack() as stack:
        beatmap = stack.enter_context(Beatmap.from_file(str(RESOURCES / case["beatmap"])))
        ruleset = stack.enter_context(Ruleset.from_id(case["ruleset"]))
        mods = stack.enter_context(ModsCollection.create())
        acronyms = case["mods"] or ""
        for index in range(0, len(acronyms), 2):
            mods.add(Mod.create(acronyms[index : index + 2]))

        difficulty = stack.enter_context(create_difficulty_calculator(ruleset, beatmap))
        actual = difficulty.calculate(mods)
        if case["score"] is not None:
            performance = stack.enter_context(create_performance_calculator(ruleset))
            actual = performance.calculate(
                ruleset,
                beatmap,
                mods,
                ScoreInfo(**case["score"]),
                actual,
            )

        assert type(actual) is getattr(attributes, case["attributes"])
        values = asdict(actual)
        assert values.keys() == case["expected"].keys()
        for name, expected in case["expected"].items():
            value = values[name]
            if isinstance(value, float) and expected is not None:
                assert value == pytest.approx(expected, rel=0, abs=0.00001), name
            else:
                assert value == expected, name
