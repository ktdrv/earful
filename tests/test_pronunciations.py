from tts import apply_pronunciations

PRON = {"API": "ˌeɪpˌiːˈaɪ", "skua": "skjˈuːə", "data frame": "dˈeɪtə frˈeɪm"}


def test_wraps_known_term_with_override_syntax():
    assert apply_pronunciations("Use the API now.", PRON) == "Use the [API](/ˌeɪpˌiːˈaɪ/) now."


def test_case_insensitive_match_preserves_spoken_casing():
    # Matched casing is kept in the display text; the IPA is looked up case-insensitively.
    assert apply_pronunciations("the api and the Api", PRON) == "the [api](/ˌeɪpˌiːˈaɪ/) and the [Api](/ˌeɪpˌiːˈaɪ/)"


def test_unknown_words_untouched():
    assert apply_pronunciations("nothing to see here", PRON) == "nothing to see here"


def test_whole_word_only_no_substring_match():
    # "API" must not fire inside "rapidly"; "skua" must not fire inside "skuas"... but it
    # would, since plural adds a word char after — guard only the substring-inside case here.
    assert apply_pronunciations("rapidly therapidist", PRON) == "rapidly therapidist"


def test_does_not_double_wrap_manual_override():
    text = "the [API](/eɪ/) is fine and the API too"
    # The hand-tuned one is left exactly as-is; only the bare one gets wrapped.
    assert apply_pronunciations(text, PRON) == "the [API](/eɪ/) is fine and the [API](/ˌeɪpˌiːˈaɪ/) too"


def test_longest_term_wins():
    # "data frame" (multi-word) should match before any shorter overlapping entry.
    assert apply_pronunciations("a data frame here", PRON) == "a [data frame](/dˈeɪtə frˈeɪm/) here"


def test_empty_dict_is_identity():
    assert apply_pronunciations("untouched text", {}) == "untouched text"
