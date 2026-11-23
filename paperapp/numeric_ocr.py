"""Correct OCR lookalikes in an explicit p-value comparison."""

import re

P_VALUE = re.compile(r"\b[pP]\s*[<>=≤≥＜＞＝]\s*(?P<value>[.．][0-9OoIl]+)(?![\w.])")
LOOKALIKES = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})


def normalize_p_values(text: str) -> str:
    return P_VALUE.sub(lambda match: match[0][:match.start("value") - match.start()]
                       + match["value"].translate(LOOKALIKES), text)
