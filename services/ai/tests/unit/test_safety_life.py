"""P10.10 danger families: vehicle accidents and other life-safety situations at a Jordanian university.

Production chat (2026-11-06): "the bus made an accident" was filed as medium. Each family below must fire in
English, Arabic and Arabizi, and the everyday look-alikes must stay silent (the official non-high gate is in
test_safety.py).
"""

from __future__ import annotations

import pytest
import yaml

from campuspulse_ai.adapters.guards.bank import compile_bank
from campuspulse_ai.adapters.guards.safety import SafetyGuard
from campuspulse_ai.adapters.preprocess.normalizer import DefaultNormalizer
from campuspulse_ai.config.paths import CONFIG_DIR, LEXICONS

MAX_TOKENS = yaml.safe_load((CONFIG_DIR / "train.yaml").read_text(encoding="utf-8"))["guards"]["max_tokens"]

DANGER = [
    # vehicle accidents
    "the bus made an accident",
    "The university bus had an accident near the north gate",
    "a car hit a student in front of the main gate",
    "there was a crash on the road to campus",
    "الباص عمل حادث",
    "صار حادث عند البوابه الشماليه",
    "el bas 3emel 7adeth",
    "sar 7adeth 3and el bawwabe",
    # fights and assault
    "a fight broke out in the cafeteria",
    "students are fighting outside building M",
    "my friend was attacked near the parking",
    "في طوشه كبيره عند كليه الهندسه",
    "الطلاب عم يتضاربوا عند البوابه",
    "fi 6osheh kbeere 3and el maktabe",
    # harassment
    "a man keeps following me around campus",
    "someone is harassing girls near the library",
    "في واحد عم يلاحقني من الصبح",
    # medical
    "a student collapsed in the lecture hall",
    "my classmate is having an asthma attack in the lab",
    "please call an ambulance a student fainted",
    "she fell and hit her head, she is not moving",
    "صاحبي صار معه جلطه بالقاعه",
    "اطلبوا الاسعاف في طالبه وقعت عن الدرج",
    "a student has heatstroke at the graduation rehearsal",
    "nawbet rabw la zamilti bel lab",
    # animals
    "stray dogs are chasing students near the dorms",
    "a scorpion stung my friend in the dorm",
    "there is a snake in the classroom",
    "الكلاب هجموا على طالبه عند السكن",
    "el klab hajamo 3ala 6aleb",
    # missing person, floods, earthquake, explosion, burns
    "my roommate is missing since yesterday",
    "flash flood on the road and the bus is stuck",
    "an earthquake just hit and the building is shaking",
    "there was an explosion in the chemistry lab",
    "acid splashed in her eyes in the lab",
    "السيول جرفت سياره عند مدخل الجامعه",
    "صوت انفجار من المختبر",
]

SILENT = [
    "I want to appeal my grade, طعن بالعلامه",
    "my head is going to explode from this exam",
    "بطاقتي الجامعيه مفقوده",
    "the student is missing the lab today",
    "I accidentally deleted my assignment",
    "the portal crashed while I was submitting",
    "how do I join the earthquake drill?",
    "we had a fight with the registration system all day",
    "the bus is late again",
    "I need a medical excuse because I broke my arm last month",
    "the stray dogs near the gate need to be handled",
]


@pytest.fixture(scope="module")
def check():
    path = LEXICONS / "safety.yaml"
    guard = SafetyGuard(compile_bank(path, "danger"), compile_bank(path, "distress"))
    normalizer = DefaultNormalizer.from_lexicons(LEXICONS, MAX_TOKENS)
    return lambda text: guard.inspect(normalizer.normalize(text)).kind


@pytest.mark.parametrize("text", DANGER)
def test_life_safety_reports_are_danger(check, text: str) -> None:
    assert check(text) == "danger", text


@pytest.mark.parametrize("text", SILENT)
def test_everyday_look_alikes_stay_silent(check, text: str) -> None:
    assert check(text) == "none", text
