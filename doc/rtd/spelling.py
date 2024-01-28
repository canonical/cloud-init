import pathlib
import re

import enchant


class WordListFilter(enchant.tokenize.Filter):
    word_list = "spelling_word_list.txt"
    regex_list = "spelling_regex_list.txt"

    def __init__(self, *args, **kwargs):
        """Use two files for ignoring correctly spelled words

        - spelling_word_list.txt: a list of exact matches to ignore
        - spelling_regex_list.txt: a list of regular expressions to ignore

        Splits tokens on "/" and "-".
        """
        super().__init__(*args, *kwargs)
        directory = pathlib.Path(__file__).parent
        with open(directory.joinpath(self.word_list)) as f:
            lines = f.read().splitlines()
            self._validate_lines(lines)
            self.word_set = set(lines)
            print(f"Loaded {self.word_list}: {lines})")
        with open(directory.joinpath(self.regex_list)) as f:
            regex_lines = f.read().splitlines()
            self.regex_set = set(regex_lines)
            print(f"Loaded {self.regex_list}: {regex_lines}")

    def _validate_lines(self, lines):
        """Assert that the word_list file is legible and orderly"""
        for line in lines:
            if line != line.lower():
                raise Exception(
                    f"Uppercase characters in {self.word_list} detected. "
                    "Please use lowercase characters for legibility."
                )
        if lines != sorted(lines):
            first_missordered = next_item = previous_item = None
            for item_a, item_b in zip(lines, sorted(lines)):
                if first_missordered:
                    next_item = item_a
                    break
                elif item_a != item_b:
                    first_missordered = item_a
                else:
                    previous_item = item_a
            unordered = (
                f"[..., {previous_item}, {first_missordered}, "
                f"{next_item}, ...]"
            )
            raise Exception(
                f"Unsorted {self.word_list} detected. "
                f"Please sort for legibility. Unordered list: {unordered}"
            )

    def _in_word_list(self, word):
        """Lowercase match the set of words in spelling_word_list.txt"""
        return word.lower() in self.word_set

    def _in_word_regex(self, word):
        """Regex match the expressions in spelling_regex_list.txt"""
        for regex in self.regex_set:
            out = re.search(regex, word)
            if out:
                return True

    def _skip(self, word):
        """Skip words and regex expressions in the allowlist files"""
        return self._in_word_list(word) or self._in_word_regex(word)

    def _split(self, word):
        """split words into sub-tokens on - and /"""
        if "-" in word or "/" in word:
            for i, token in enumerate(re.split("-|/", word)):
                if self._skip(token):
                    continue
                yield token, i
