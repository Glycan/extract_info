import re
import string
from itertools import (
    permutations, combinations, product, filterfalse, chain#, starmap
)
from functools import reduce, partial
from typing import List, Callable, Iterator, Tuple, Sequence
import nltk
from nltk.corpus import wordnet
import google_analyze
from utils import cache, compose, identity_function, soft_filter

Names = List[str]

# general functions

def space_dashes(text: str) -> str:
    "put spaces around dashes without spaces"
    return re.sub(r"-([^ -])", r"- \1", re.sub(r"([^ -])-", r"\1 -", text))

def contains_nonlatin(text: str) -> bool:
    return not any(map(string.printable.__contains__, text))
    # .84usec faster than using a comprehension

# combinatorial functions

## extractors

### "crude" extractors

@cache.with_cache
def nltk_extract_names(text: str) -> Names:
    "returns names using NLTK Named Entity Recognition, filters out repetition"
    names = []
    for sentance in nltk.sent_tokenize(text):
        for chunk in nltk.ne_chunk(nltk.pos_tag(nltk.word_tokenize(sentance))):
            if isinstance(chunk, nltk.tree.Tree):
                if chunk.label() == 'PERSON':
                    names.append(' '.join([c[0] for c in chunk]))
    # remove any names that contain each other
    for name1, name2 in permutations(names, 2):
        if name1 in name2:
            names.remove(name1)
    return names

def all_capitalized_extract_names(text: str) -> List[str]:
    return [
        "".join(filter(str.isalpha, word))
        for word in text.split() if word[0].isupper()
    ]

CRUDE_EXTRACTORS: List[Callable[[str], Names]] = [
    nltk_extract_names, all_capitalized_extract_names
]

### google extractor and preprocessors

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
    return " ".join([
        word for word in text.split()
        if all(c.isalpha() or c in r"-/\$%(),.:;?!" for c in word)
    ])

@cache.with_cache
def every_name(line: str) -> str:
    open("every_name_ex", "a").write(line + "\n")
    return "".join(map(
        "My name is {}. ".format,
        only_alpha(line).split()
    ))
    # explore some option for merging adjacent names?

GOOGLE_EXTRACTORS = list(map(
    partial(compose, google_extract_names),
    [only_alpha, identity_function, every_name]
))

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

UNIQUE_REFINERS = [remove_short, remove_synonyms, remove_nonlatin]

REFINERS: Sequence[Callable[[Names], Names]]
REFINERS = [identity_function] + list(map(
    partial(reduce, compose),
    chain(*(map(
        partial(combinations, UNIQUE_REFINERS),
        range(1, len(UNIQUE_REFINERS))
    )))
))

def extract_names(line: str, min_names: int, max_names: int) -> Names:
    text: str = space_dashes(line)
    def min_criteria(names: Names) -> bool:
        return len(names) >= min_names
    # does it contain nonlatin?
    google_extractions: Iterator[Names] = soft_filter(
        min_criteria,
        (extractor(text) for extractor in GOOGLE_EXTRACTORS)
    ) # if so, google needs to return min_names - nonlatin names
    crude_extractions: Iterator[Names] = soft_filter(
        min_criteria,
        (extractor(text) for extractor in CRUDE_EXTRACTORS)
    ) # set aside any nonlatin results
    consensuses: Iterator[Names] = soft_filter(
        min_criteria,
        (fuzzy_intersect(google_extraction, crude_extraction)
         for google_extraction in google_extractions
         for crude_extraction in crude_extractions)
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
        (refine(consensus) for consensus in consensuses for refine in REFINERS)
    )
    return next(refined_consensuses)
