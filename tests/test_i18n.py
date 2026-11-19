from string import Formatter

from app.i18n import TRANSLATIONS, translate


def test_languages_have_matching_keys_and_placeholders():
    russian, english = TRANSLATIONS["ru"], TRANSLATIONS["en"]
    assert russian.keys() == english.keys()
    formatter = Formatter()
    for key in russian:
        placeholders = [
            {name for _, name, _, _ in formatter.parse(translate(key, language)) if name is not None}
            for language in ("ru", "en")
        ]
        assert placeholders[0] == placeholders[1], key
