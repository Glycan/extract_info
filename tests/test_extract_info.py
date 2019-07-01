import re
import json
from typing import Dict, List, Any, Tuple, Callable
import pytest
import extract_info
import extract_names
import utils
from tools import ask, fd_print

# our code has three step and various strategies for  each step,
# which it does in order until one works
# as soon as a given strategy for this step doesn't work, it should jump
# to the next strategy for this step without trying the next steps

# this corresponds to a finate state automata
# where the symbols are the names of each strategy for each step
# and the states are the combinations of strategies for each step,
# including "not doing this step right now" as the 0th state

# because every FSA corresponds to a regex, we know that there exists a
# regex that match correct paths. we can log which strategies are called
# and see if they match the regex to test correct program flow


def correct_pattern_gen(items: List[str], suffix: str) -> str:
    if len(items) == 1:
        return items[0] + "\n" + suffix
    return f"{items[0]}\n({suffix}|{correct_pattern_gen(items[1:], suffix)})"


STEPS_STRATEGY_NAMES: List[List[str]] = [
    [strategy.__name__ for strategy in step] for step in extract_names.STEPS
]


CORRECT_PATTERN = ""
for step_strategy_names in reversed(STEPS_STRATEGY_NAMES):
    CORRECT_PATTERN = correct_pattern_gen(step_strategy_names, CORRECT_PATTERN)


def trace_extract_info_nonfixture() -> Tuple[utils.Logger, Callable]:
    logger = utils.Logger()

    def wrap_logging(funcs: List[Callable]) -> List[Callable]:
        return [logger.logged(func) for func in funcs]

    steps = {
        "refiners": wrap_logging(extract_names.REFINERS),
        "crude_extractors": wrap_logging(extract_names.CRUDE_EXTRACTORS),
        "google_extractors": wrap_logging(extract_names.GOOGLE_EXTRACTORS),
    }

    def traced_extract_info(*args: Any, **kwargs: Any) -> Any:
        result = extract_info.extract_info(*args, **steps, **kwargs)
        return result

    return (logger, traced_extract_info)


trace_extract_info_fixture = pytest.fixture(
    trace_extract_info_nonfixture, name="trace_extract_info"
)


Entry = Dict[str, List[str]]

CASES: List[Entry]
CASES = json.load(open("data/correct_cases.json", encoding="utf-8"))


@pytest.fixture(params=CASES, name="correct_case")
def correct_case_fixture(request: Any) -> Entry:
    return request.param


def test_cases(
    correct_case: Entry, trace_extract_info: Tuple[utils.Logger, Callable]
) -> None:
    logger, traced_extract_info = trace_extract_info
    stream = logger.new_stream()
    line = correct_case["line"][0]
    actual = traced_extract_info(line)
    if actual != correct_case:
        breakpoint()
        actual = extract_info.extract_info(line)
    assert actual == correct_case
    log_trace = stream.getvalue()
    assert re.fullmatch(CORRECT_PATTERN, log_trace) is not None


DIFFICULT_CASES: List[Entry]
DIFFICULT_CASES = json.load(open("data/incorrect_cases.json", encoding="utf-8"))


@pytest.fixture(params=DIFFICULT_CASES, name="difficult_case")
def difficult_case_fixture(request: Any) -> Entry:
    return request.param


@pytest.mark.skip
@pytest.mark.xfail
def test_difficult_cases(difficult_case: Entry) -> None:
    """these are examples that were marked as incorrect, if we have
    different anaswers for them that means there might be improvement"""
    line = difficult_case["line"][0]
    actual_case: Entry = extract_info.extract_info(line)
    if actual_case["names"] != difficult_case["names"]:
        correct = ask(actual_case)
        if correct:
            json.dump(
                [case for case in DIFFICULT_CASES if case != difficult_case],
                open("data/incorrect_cases.json", "w", encoding="utf-8"),
                indent=4,
            )
            json.dump(
                CASES + [actual_case],
                open("data/correct_cases.json", "w", encoding="utf-8"),
                indent=4,
            )
            fd_print("marked as a correct example")
            # just move this into the other one
    assert actual_case["names"] != difficult_case["names"]


def test_last() -> None:
    # fake test
    utils.cache.save_cache()