from __future__ import division
import sys
import csv
import re
from itertools import zip_longest
import argparse
from enum import Enum
from typing import List, Dict, Tuple, Any
from phonenumbers import PhoneNumberMatcher, format_number, PhoneNumberFormat
from extract_names import extract_names
from utils import cache


class Flags(str, Enum):
    correct = "correct"
    too_many = "too many"
    not_enough = "not enough"
    multiple_contacts = "multiple contacts"
    one_contact = "one_contact"
    all = "all"
    skipped = "skipped"

    def __str__(self) -> str:
        return self.value


EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+")

Names = List[str]
Entry = Dict[str, Names]


def space_dashes(text: str) -> str:
    "Put spaces around dashes without spaces."
    return re.sub(r"-([^ -])", r"- \1", re.sub(r"([^ -])-", r"\1 -", text))


def min_max_names(emails: List[str], phones: List[str]) -> Tuple[int, int]:
    contact_counts: Tuple[int, int] = (len(emails), len(phones))
    # if there's 1 email and 3 phones, min_names should be 1
    # but if there's 0 email and 1 phone, it should be 1, not 0
    min_names: int = max(1, min(contact_counts))
    max_names: int = max(contact_counts)
    # maybe add min, likely_max, absolute_max to distingish max vs sum?
    return (min_names, max_names)


def decide_exit_type(names: List[str], min_names: int, max_names: int) -> Flags:
    names_count = len(names)
    if names_count <= max_names:
        if names_count < min_names:
            return Flags.not_enough
        return Flags.correct
    return Flags.too_many


def extract_info(
    raw_line: str, flags: bool = False, **extract_names_kwargs: Any
) -> Dict[str, List[str]]:
    line: str = raw_line.replace("'", "").replace("\n", "")
    emails: List[str] = EMAIL_RE.findall(line)
    phones: List[str] = [
        format_number(match.number, PhoneNumberFormat.INTERNATIONAL)
        for match in PhoneNumberMatcher(line, "US")
    ]
    min_names, max_names = min_max_names(emails, phones)
    names: List[str]
    if max_names == 0:
        names = ["skipped"]
    else:
        clean_line = space_dashes(line)
        names = extract_names(clean_line, min_names, max_names, **extract_names_kwargs)
    print(".", end="")
    sys.stdout.flush()
    result = {"line": [line], "emails": emails, "phones": phones, "names": names}
    if flags:
        if not max_names:
            result["flags"] = [Flags.skipped]
            return result
        result["flags"] = [
            (Flags.one_contact if max_names == 1 else Flags.multiple_contacts),
            decide_exit_type(names, min_names, max_names),
            Flags.all,
        ]
    return result


def save_entries(entries: List[Entry], fname: str) -> None:
    header = ["line", "emails", "phones", "names"]
    with open(fname, "w", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for entry in entries:
            contact_infos = [entry[heading] for heading in header]
            contacts = zip_longest(*contact_infos, fillvalue="")
            for contact in contacts:
                writer.writerow(list(contact))


def metrics(entries: List[Entry]) -> Dict:
    entry_types = {
        flag: [entry for entry in entries if flag in entry["flags"]] for flag in Flags
    }
    counts = dict(zip(entry_types.keys(), map(len, entry_types.values())))
    for flag in list(Flags)[:4]:
        print("{}: {:.2%}. ".format(flag, counts[flag] / counts[Flags.all]), end="")
    print()
    return locals()


def main() -> Dict:
    parser = argparse.ArgumentParser("extract names and contact info from csv")
    parser.add_argument("-i", "--input", default="data/trello.csv")
    parser.add_argument("-o", "--output", default="data/info.csv")
    args = parser.parse_args()
    lines = list(csv.reader(open(args.input, encoding="utf-8")))[1:]
    with cache:
        entries = [extract_info(line[0], flags=True) for line in lines]
    save_entries(entries, args.output)
    return metrics(entries)


if __name__ == "__main__":
    debugging = main()
