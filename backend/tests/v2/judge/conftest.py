from copy import deepcopy

import pytest

from app.v2.judge_examples import make_judge_example


@pytest.fixture
def examples():
    # This helper uses asyncio.run; construct the authored examples before any
    # async test starts. They remain explicitly labelled fixtures.
    return {
        kind: make_judge_example(kind) for kind in ("complete", "partial", "unscored")
    }


@pytest.fixture
def drafts(examples):
    fields = {
        "summary",
        "recommendation",
        "pros",
        "cons",
        "next_steps",
        "key_interactions",
        "limitations",
    }
    result = {}
    for kind, (_, example) in examples.items():
        draft = example.model_dump(mode="json", include=fields)
        draft[
            "key_interactions"
        ] = []  # A lone message does not demonstrate an interaction.
        result[kind] = deepcopy(draft)
    return result
