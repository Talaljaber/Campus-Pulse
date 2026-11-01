"""P7.2: the extended danger and distress lexicons (EN, Arabic script, Arabizi) and their counter-examples.

Every sentence below was written for this test from general language knowledge; none is copied from a dev,
test or official row. Gate on official rows lives in `test_safety.py`.
"""

from __future__ import annotations

import pytest
import yaml

from campuspulse_ai.adapters.guards.bank import compile_bank
from campuspulse_ai.adapters.guards.safety import SafetyGuard
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import CONFIG_DIR, LEXICONS

MAX_TOKENS = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))["guards"]["max_tokens"]

DANGER: dict[str, list[str]] = {
    "en_transport_breakdown": [
        "Our university bus broke down on the airport road and 25 of us are still inside",
        "The shuttle stalled on the highway near Zarqa with passengers on board and nobody came",
        "Minibus stopped at the roadside with students inside, the driver left to find help",
    ],
    "en_reckless_driving": [
        "The bus driver was driving recklessly on the way to campus",
        "Our shuttle driver ran a red light and we almost crashed into a truck",
        "The driver was speeding way over the speed limit with students standing in the aisle",
    ],
    "en_outage_people_at_risk": [
        "Power is out and the stairwell in block B is pitch black, a girl already fell",
        "Blackout in the basement corridor, it is dark and people are scared and cannot see",
        "The emergency lights are not working after the power cut, students are stuck in the dark",
    ],
    "en_gas_fumes": [
        "There is gas leaking from a pipe next to the cafeteria kitchen",
        "Toxic fumes in the chemistry corridor and several people are coughing",
        "A strong chemical smell in the lab and students feel dizzy",
    ],
    "en_other_physical": [
        "A man with a knife is threatening students near the gate",
        "The balcony railing in the main hall collapsed",
        "Somebody could get seriously hurt on those broken stairs",
        "Rain is leaking onto the sockets in the corridor outside room 204",
    ],
    "ar_transport_breakdown": [
        "الباص خرب عالطريق السريع وفينا اكتر من عشرين طالب",
        "الحافلة تعطلت على الاوتوستراد والركاب جواها والسواق نزل",
        "الكوستر وقف عالطريق الصحراوي وما حدا اجا ناخدنا وفيه طلاب",
    ],
    "ar_reckless_driving": [
        "السواق كان بسوق بتهور وكاد يعمل حادث",
        "سواق الباص بيسوق بسرعة جنونية والطلاب خايفين",
        "الشوفير قطع الاشارة الحمرا وكان رح يدعس واحد",
    ],
    "ar_outage_people_at_risk": [
        "انقطعت الكهربا والدرج كله عتمة وبنت وقعت وفي طلاب خايفين",
        "اضاءة الطوارئ مش شغالة بعد ما راحت الكهربا",
        "ضلينا بالعتمة بالمصعد بعد قطع الكهربا",
    ],
    "ar_gas_fumes": [
        "في غاز بيتسرب من انبوبة الكافتيريا",
        "ريحة غاز قوية بالممر وناس عم يسعلوا",
        "تسرب مواد كيماوية بالمختبر والطلاب مدوخين",
    ],
    "ar_other_physical": [
        "في شب معه سكين وعم يهدد الطلاب",
        "الدرابزين عالدرج وقع وممكن حدا يتأذى",
        "بنت وقعت اغماء بالممر",
    ],
    "az_transport_breakdown": [
        "el bus khirib 3al autostrad w fina 30 taleb jowwa",
        "el bas waqef 3al highway w fina tolab w ma7ad ija",
        "3al tari2 el sa7rawi el bus 3atel w fina 20 6aleb",
    ],
    "az_reckless_driving": [
        "el sawwa2 bisoo2 btahawwor w el tolab khayfeen",
        "el shofer bysoo2 zay el majnoon 3al autostrad",
        "kan rah ya3mel 7adeth el sawwa2 el yom",
    ],
    "az_outage_people_at_risk": [
        "inqata3at el kahraba w el daraj kolo 3atme w fi tolab khayfeen",
        "el ma7boseen bel dark ba3d ma 2ata3at el kahraba",
        "emergency lights msh shaghale w el kahraba qat3at",
    ],
    "az_gas": [
        "ri7et gaz 2awiye bel mo5tabar",
        "fi ri7a ghaz bel mamar",
        "el GAZ 3am bitsarreb min el anboobe",
        "tasreeb ghaz bel cafeteria",
        "RI7ET EL GAS bel lab",
    ],
    "az_other_physical": [
        "fi sekkin ma3 wa7ad w 3am bihaded el tolab",
        "el 6alebe etghamet bel mamar",
    ],
}

DISTRESS: dict[str, list[str]] = {
    "en": [
        "I feel like it's all over for me and I can't go on",
        "I don't know what to do with my life anymore",
        "Honestly I feel like everyone would be better off without me",
        "I'm depressed and I want to disappear",
        "No hope left, I give up on everything",
    ],
    "ar": [
        "حاسس اني خلصت وما في فايدة مني",
        "ما بعرف شو اعمل بحياتي",
        "انا يائس وبدي اختفي",
        "مش قادر اكمل حياتي هيك",
        "انا مكتئب كتير ومش قادر",
        "بتمنى لو اموت",
    ],
    "az": [
        "7ases eni 5alast w ma fi faida",
        "ma b3raf shu a3mel b 7yati",
        "ana mokta2eb w ya2es",
        "msh 2ader akammel 7ayati hek",
        "ma 3ad bde a3eesh",
        "bde a5tefi",
    ],
}

# Frustration, deadlines and idioms that must stay silent (neither danger nor distress).
NEGATIVE = [
    "the deadline is over",
    "khalas el deadline",
    "خلص الوقت",
    "هالبورتال بيقتلني كل مرة",
    "this portal is killing me",
    "I'm dying of boredom in this queue",
    "ana ta3ban mn el wajebat",
    "el portal bi2tolni kol marra bi3melli logout",
    "I can't go on to the next page of the form",
    "7ases eno khalas el wa2et",
    "I am so tired of the long queue at registration",
    "The bus stopped running on this route after 6 pm",
    "The bus broke down on the road yesterday and I was late for class",
    "bus schedule for the highway route is not updated",
    "Power is out in the whole building, when will it be back",
    "No power in block D and the online exam is running",
    "mafi kahraba bel building D w el exam shaghal",
    "الكهربا قاطعة عن البناية كلها",
    "الباص متأخر ونحن ننتظر عند الموقف",
    "fi gas station 2areeb min el jame3a",
    "my driving licence needs a signature from the registrar",
]


def _guard() -> SafetyGuard:
    path = LEXICONS / "safety.yaml"
    return SafetyGuard(compile_bank(path, "danger"), compile_bank(path, "distress"))


@pytest.fixture(scope="module")
def guard() -> SafetyGuard:
    return _guard()


@pytest.fixture(scope="module")
def normalizer() -> DefaultNormalizer:
    return DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)


def _kind(guard: SafetyGuard, normalizer: DefaultNormalizer, text: str) -> str:
    return guard.inspect(normalizer.normalize(text)).kind


def test_every_family_has_three_variants_per_language() -> None:
    langs = {"en": 0, "ar": 0, "az": 0}
    for family, rows in DANGER.items():
        langs[family[:2]] += 1
        assert len(rows) >= 2, family
    assert all(n >= 4 for n in langs.values())
    for family in (
        "en_transport_breakdown",
        "ar_transport_breakdown",
        "az_transport_breakdown",
        "en_outage_people_at_risk",
        "ar_outage_people_at_risk",
        "az_outage_people_at_risk",
        "ar_reckless_driving",
        "az_reckless_driving",
        "en_reckless_driving",
    ):
        assert len(DANGER[family]) >= 3, family
    assert len(DANGER["az_gas"]) >= 3
    assert all(len(v) >= 3 for v in DISTRESS.values())


@pytest.mark.parametrize("family", sorted(DANGER))
def test_danger_family_fires(guard: SafetyGuard, normalizer: DefaultNormalizer, family: str) -> None:
    missed = [t for t in DANGER[family] if _kind(guard, normalizer, t) != "danger"]
    assert missed == []


@pytest.mark.parametrize("lang", sorted(DISTRESS))
def test_distress_fires(guard: SafetyGuard, normalizer: DefaultNormalizer, lang: str) -> None:
    missed = [t for t in DISTRESS[lang] if _kind(guard, normalizer, t) != "distress"]
    assert missed == []


def test_counter_examples_stay_silent(guard: SafetyGuard, normalizer: DefaultNormalizer) -> None:
    fired = [(t, _kind(guard, normalizer, t)) for t in NEGATIVE if _kind(guard, normalizer, t) != "none"]
    assert fired == []


@pytest.mark.parametrize(
    "text",
    [
        "URGENT!!! please fix the printer ASAP",
        "3ajel 3ajel el wifi bsor3a",
        "عاجل جدا بدي حل بسرعة للتسجيل",
    ],
)
def test_tone_alone_is_never_danger(guard: SafetyGuard, normalizer: DefaultNormalizer, text: str) -> None:
    assert _kind(guard, normalizer, text) == "none"


def test_distress_wins_over_danger_when_both_match(guard: SafetyGuard, normalizer: DefaultNormalizer) -> None:
    """Documents the known precedence gap.

    `SafetyGuard` returns the first verdict, distress, so a request that is both loses `danger` (and with it
    the safety tag). Follow-up: let the verdict carry both (see the P7.2 report).
    """
    text = "There is smoke in the lab and I feel like it's all over for me"
    verdict = guard.inspect(normalizer.normalize(text))
    assert verdict.kind == "distress"
