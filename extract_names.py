import string
from itertools import permutations, combinations, filterfalse
from functools import reduce, wraps
from typing import List, Callable, Iterator, Sequence, Tuple
import google_analyze
from utils import cache, compose, soft_filter

Names = List[str]
NameAttempts = Iterator[Names]
# general functions


def contains_nonlatin(text: str) -> bool:
    return not any(map(string.printable.__contains__, text))
    # .84usec faster pcall than using a comprehension


# combinatorial functions

## extractors

#### google extractor and preprocessors


@cache.with_cache
def google_extract_names(text: str) -> Names:
    """
    returns names using Google Cloud Knowledge Graph Named Entity Recognition
    skips non-ASCII charecters
    """
    latin_text = "".join(filter(string.printable.__contains__, text))
    return google_analyze.extract_entities(latin_text)
    # TO DO: merge adjacent names


@cache.with_cache
def only_alpha(text: str) -> str:
    "remove words that don't have any alphabetical chareceters or -"
    return " ".join(
        [
            word
            for word in text.split()
            if all(c.isalpha() or c in r"-/\$%(),.:;?!" for c in word)
        ]
    )


def no_preprocess(text: str) -> str:
    return text


@cache.with_cache
def every_name(text: str) -> str:
    return "".join(map("My name is {}. ".format, only_alpha(text).split()))
    # explore some option for merging adjacent names?


GOOGLE_PREPROCESSES: List[Callable[[str], str]] = [
    only_alpha,
    no_preprocess,
    every_name,
]

GOOGLE_EXTRACTORS: List[Callable[[str], Tuple[str, Names]]] = [
    wraps(composed_fn)(lambda text: (text, composed_fn(text)))
    for composed_fn in [
        compose(google_extract_names, preprocess) for preprocess in GOOGLE_PREPROCESSES
    ]
]

## "crude" extractors


@cache.with_cache
def nltk_extract_names(text: str) -> Names:
    "returns names using NLTK Named Entity Recognition, filters out repetition"
    import nltk

    names = []
    for sentance in nltk.sent_tokenize(text):
        for chunk in nltk.ne_chunk(nltk.pos_tag(nltk.word_tokenize(sentance))):
            if isinstance(chunk, nltk.tree.Tree):
                if chunk.label() == "PERSON":
                    names.append(" ".join([c[0] for c in chunk]))
    # remove any names that contain each other
    for name1, name2 in permutations(names, 2):
        if name1 in name2:
            names.remove(name1)
    return names


def all_capitalized_extract_names(text: str) -> List[str]:
    return [
        "".join(filter(str.isalpha, word))
        for word in text.split()
        if word[0].isupper()
        and not all(map(str.isupper, word[1:]))  # McCall is a name, but ELISEVER isn't
    ]


Extractors = Sequence[Callable[[str], Names]]

CRUDE_EXTRACTORS: Extractors = [nltk_extract_names, all_capitalized_extract_names]


## refiners
def fuzzy_intersect(google_names: Names, crude_names: Names) -> Names:
    if google_names == []:
        return crude_names
    intersect = []
    for crude_name in crude_names:
        if contains_nonlatin(crude_name):
            intersect.append(crude_name)
            # google doesn't work with non-latin characters
            # so we ignore it in those cases
        else:
            for google_name in google_names:
                if [part for part in crude_name.split() if part in google_name]:
                    intersect.append(crude_name)
    return intersect


@cache.with_cache
def remove_synonyms(names: Names) -> Names:
    "removes words that have wordnet synonyms"
    from nltk.corpus import wordnet

    return [
        name
        for name in names
        if not any(len(wordnet.synsets(word)) > 1 for word in name.split())
    ]


@cache.with_cache
def remove_nonlatin(names: Names) -> Names:
    """ keep names that contain no nonlatin chars"""
    return list(filterfalse(contains_nonlatin, names))
    # this is .5 usec faster than using a comprehension


def remove_short(names: Names) -> Names:
    return [name for name in names if len(name) > 2]


Refiners = List[Callable[[Names], Names]]

UNIQUE_REFINERS: Refiners = [remove_short, remove_synonyms, remove_nonlatin]


# REFINERS: Refiners = []
# for i in range(1, len(UNIQUE_REFINERS)):
#     for combination in combinations(UNIQUE_REFINERS, i):
#         refiner: Callable[[Names], Names] = reduce(compose, combination)
#         REFINERS.append(refiner)


REFINERS: Refiners = [lambda names: names] + [
    reduce(compose, combination)
    for i in range(1, len(UNIQUE_REFINERS))
    for combination in combinations(UNIQUE_REFINERS, i)
]

STAGES: Sequence[Sequence[Callable]] = (GOOGLE_EXTRACTORS, CRUDE_EXTRACTORS, REFINERS)


def extract_names(  # pylint: disable=dangerous-default-value,too-many-arguments
    text: str,
    min_names: int,
    max_names: int,
    google_extractors: Extractors = GOOGLE_EXTRACTORS,
    crude_extractors: Extractors = CRUDE_EXTRACTORS,
    refiners: Refiners = REFINERS,
    # TODO: refactor the default arguments into one
) -> Names:
    def filter_min_criteria(attempts: NameAttempts) -> NameAttempts:
        yield from filter(min_names.__le__, attempts)
        yield []

    # does it contain nonlatin?
    google_extractions: Iterator[Names] = soft_filter(
        min_criteria, (extractor(text) for extractor in google_extractors)
    )  # if so, google needs to return min_names - nonlatin names
    crude_extractions: Iterator[Names] = soft_filter(
        min_criteria, (extractor(text) for extractor in crude_extractors)
    )  # set aside any nonlatin results
    consensuses: Iterator[Names] = soft_filter(
        min_criteria,
        (
            fuzzy_intersect(google_extraction, crude_extraction)
            for google_extraction in google_extractions
            for crude_extraction in crude_extractions
        ),
    )
    # equal intersect, don't special-case google
    # latin_consensuses = .. as above ...
    # all_consensuses = filter(
    #   min_criteria,
    #   map(
    #       lambda tuple:tuple[0]+tuple[1],
    #       product([nonlatin_names, []], latin_consensues)
    #   )
    #   r1, r2, remove_nonlatin, remove_nonlatin(r1(, ...
    refined_consensuses: Iterator[Names] = soft_filter(
        lambda consensus: min_names <= len(consensus) <= max_names,
        (refine(consensus) for consensus in consensuses for refine in refiners),
    )
    return next(refined_consensuses)
