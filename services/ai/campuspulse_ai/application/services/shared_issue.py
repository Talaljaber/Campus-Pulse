"""Conservative, rule-based eligibility for shared campus problems (P10.3)."""

from __future__ import annotations

import re

from campuspulse_ai.domain.labels import Category

SHARED_CATEGORIES = frozenset({Category.FACILITIES, Category.IT_SUPPORT, Category.TRANSPORTATION})
_PERSONAL = re.compile(
    r"\b(?:my|mine|account|password|grade|fee|invoice|registration|tuition|mark|transcript)\b"
    r"|(?:حسابي|كلمة السر|علامتي|درجتي|رسومي|تسجيلي|فاتورتي)",
    re.IGNORECASE,
)
_FAULT = re.compile(
    r"\b(?:outage|down|broken|not working|stopped|cancelled|canceled|no electricity|power cut|"
    r"wifi|wi-fi|internet|bus late|late bus|buses late|electricity|blackout)\b"
    r"|(?:عطل|معطل|مقطوع|انقطاع|ما بشتغل|مش شغال|الكهربا|النت|الواي فاي|الباص|الباصات)"
    r"|\b(?:ma beshteghel|ma bsht8l|wifi down|net down|bus late)\b",
    re.IGNORECASE,
)


def shared_issue_eligible(category: Category, text: str, *, group_cue: bool = False) -> bool:
    """Require a shared-service category and fault signal; personal cues always veto."""
    if category not in SHARED_CATEGORIES or _PERSONAL.search(text):
        return False
    return bool(_FAULT.search(text) or group_cue)
