"""Unit tests for deterministic TTS speech normalization."""

import json
from pathlib import Path
import unittest

from src.speech_normalizer import is_non_audio_block, normalize_for_speech


ROOT_DIR = Path(__file__).resolve().parent.parent


class TestSpeechNormalizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = json.loads((ROOT_DIR / "config" / "pronunciations.json").read_text(encoding="utf-8"))
        cls.pronunciations = raw["replacements"]

    def test_luke_parsha_examples(self) -> None:
        self.assertEqual(
            normalize_for_speech("References: Genesis 1:1-6:8; Isaiah 42:5-43:10; John 1:1-5."),
            "References: Genesis chapter 1 verse 1 through chapter 6 verse 8; "
            "Isaiah chapter 42 verse 5 through chapter 43 verse 10; "
            "John chapter 1, verses 1 through 5.",
        )
        self.assertEqual(
            normalize_for_speech("“What has been will be again” (Eccl. 1:9)."),
            "“What has been will be again” (Ecclesiastes chapter 1 verse 9).",
        )
        self.assertEqual(normalize_for_speech("(Phil.2:8)"), "(Philippians chapter 2 verse 8)")
        self.assertEqual(normalize_for_speech("(Gal. 6:9 )"), "(Galatians chapter 6 verse 9)")

    def test_complex_corpus_citation_shapes(self) -> None:
        self.assertEqual(
            normalize_for_speech("Hebrews 8:6;12:24."),
            "Hebrews chapter 8 verse 6, and chapter 12 verse 24.",
        )
        self.assertEqual(
            normalize_for_speech("Acts 1:1-9 and 2.1-47; 10:44-46; 19:6; 1 Cor. 14."),
            "Acts chapter 1, verses 1 through 9; chapter 2, verses 1 through 47; "
            "chapter 10, verses 44 through 46; and chapter 19 verse 6; "
            "First Corinthians chapter 14.",
        )
        self.assertEqual(
            normalize_for_speech("(1 Corinthians16:13)"),
            "(First Corinthians chapter 16 verse 13)",
        )
        self.assertEqual(normalize_for_speech("(Gen, 31:3)"), "(Genesis chapter 31 verse 3)")
        self.assertEqual(normalize_for_speech("(32:1)"), "(chapter 32 verse 1)")
        self.assertEqual(
            normalize_for_speech("( 32:22-32)"),
            "(chapter 32, verses 22 through 32)",
        )
        self.assertEqual(
            normalize_for_speech("(See 27:28-29)"),
            "(See chapter 27, verses 28 through 29)",
        )
        self.assertEqual(
            normalize_for_speech("Revelation 3 :15-16"),
            "Revelation chapter 3, verses 15 through 16",
        )
        self.assertEqual(
            normalize_for_speech("from Romans 1: 21-31 NASB."),
            "from Romans chapter 1, verses 21 through 31, New American Standard Bible.",
        )
        self.assertEqual(
            normalize_for_speech("(1 John 5:5:24)"),
            "(First John chapter 5, verses 5 and 24)",
        )
        self.assertEqual(
            normalize_for_speech("Jude 1:1-10-13"),
            "Jude chapter 1, verses 1 through 13",
        )
        self.assertEqual(
            normalize_for_speech("Genesis 23:1-25:18; 1 Kings 1:1-31"),
            "Genesis chapter 23 verse 1 through chapter 25 verse 18; "
            "First Kings chapter 1, verses 1 through 31",
        )
        self.assertEqual(
            normalize_for_speech("Matt. 10:28, 2 Thess. 1:9, Rev. 20:10"),
            "Matthew chapter 10 verse 28, Second Thessalonians chapter 1 verse 9, "
            "Revelation chapter 20 verse 10",
        )
        self.assertEqual(
            normalize_for_speech("Ezek. 40-46"),
            "Ezekiel chapters 40 through 46",
        )
        self.assertEqual(
            normalize_for_speech("Psalm 121:3-4 and Psalm 19:8"),
            "Psalm 121, verses 3 through 4 and Psalm 19 verse 8",
        )
        self.assertEqual(
            normalize_for_speech('Jeremiah ch. 3:11-18 and as in ”really” and “History“ or "salt"standards'),
            'Jeremiah chapter 3, verses 11 through 18 and as in “really” and “History” or "salt" standards',
        )
        self.assertEqual(
            normalize_for_speech("See Samual 12:7-14."),
            "See Samuel chapter 12, verses 7 through 14.",
        )

    def test_non_bible_and_false_positive_guards(self) -> None:
        self.assertEqual(
            normalize_for_speech("revealed in Strong’s Heb. 5680 as"),
            "revealed in Strong's Hebrew number 5680 as",
        )
        self.assertEqual(normalize_for_speech("Commentary; p. 969."), "Commentary; page 969.")
        self.assertEqual(
            normalize_for_speech("Pgs. Pgs. Pgs. 347 332"),
            "Pages 347 332",
        )
        self.assertEqual(normalize_for_speech("(v. 5)"), "(verse 5)")
        self.assertEqual(normalize_for_speech("at 7:30 a.m. today"), "at 7:30 a.m. today")
        self.assertEqual(normalize_for_speech("Is 5 too many?"), "Is 5 too many?")
        self.assertEqual(normalize_for_speech("In 1965, he served."), "In 1965, he served.")
        self.assertEqual(normalize_for_speech("10/7 was tragic."), "10/7 was tragic.")
        self.assertEqual(normalize_for_speech("Dr. Hutch and Rev. Smith"), "Dr. Hutch and Rev. Smith")

    def test_bracket_categories(self) -> None:
        self.assertEqual(normalize_for_speech("them.[1] And[4B] now"), "them. And now")
        self.assertEqual(
            normalize_for_speech("outraging [of] the order and death of her [young],"),
            "outraging of the order and death of her young,",
        )
        self.assertEqual(
            normalize_for_speech("sent messengers [to Esau] today."),
            "sent messengers to Esau today.",
        )
        self.assertEqual(
            normalize_for_speech("If you abide [obey] in my word"),
            "If you abide, obey, in my word",
        )
        self.assertEqual(
            normalize_for_speech("words [Note: Truly hear and receive [act upon] them.] Yes."),
            "words — Note: Truly hear and receive, act upon, them. Yes.",
        )
        self.assertEqual(
            normalize_for_speech("follow me {clearly--submit to my commandments} now"),
            "follow me — clearly — submit to my commandments — now",
        )

    def test_slashes_caps_states_and_symbols(self) -> None:
        self.assertEqual(
            normalize_for_speech("his/her Ecclesia/Church and/or Israel/Ephraim"),
            "his or her Ecclesia or Church and or Israel or Ephraim",
        )
        self.assertEqual(
            normalize_for_speech("noted for the 1/2 hour of silence"),
            "noted for the half hour of silence",
        )
        self.assertEqual(
            normalize_for_speech("YHWH and YHVH's LORD said"),
            "Yahweh and Yahweh's Lord said",
        )
        self.assertEqual(
            normalize_for_speech("(Matthew 16:24-27; brackets added by C.V. )"),
            "(Matthew chapter 16, verses 24 through 27)",
        )
        self.assertEqual(
            normalize_for_speech("moved to Tulsa, OK. and Cape Cod, MA."),
            "moved to Tulsa, Oklahoma. and Cape Cod, Massachusetts.",
        )
        self.assertEqual(
            normalize_for_speech("Conclusion --> Prepare #1 T&G action–-fruit i. e. good (a) and (b)"),
            "Conclusion — Prepare number 1 T and G action — fruit that is, good (A) and (B)",
        )
        self.assertEqual(
            normalize_for_speech("WHOSE PATH ARE YOU ON?"),
            "Whose Path Are You On?",
        )

    def test_pronunciations_applied_cleanly(self) -> None:
        res = normalize_for_speech("B’resheit 32:3 and Selah.", self.pronunciations)
        self.assertEqual(res, "Behray sheet chapter 32 verse 3 and Say lah.")

    def test_non_audio_block(self) -> None:
        self.assertTrue(is_non_audio_block("(Audio available to subscribers)"))
        self.assertTrue(is_non_audio_block("AUDIO. Click the black triangle located above."))
        self.assertFalse(is_non_audio_block("Yeshua is our High Priest."))
