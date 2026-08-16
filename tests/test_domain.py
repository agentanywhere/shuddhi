import domain

CODE = """
import os

def process_orders(orders):
    total = 0
    for o in orders:
        total += o.amount
    return total

class OrderProcessor:
    pass
"""

BFSI_EN = (
    "The Reserve Bank of India kept the repo rate unchanged. Banks are expected "
    "to hold interest rate on savings account deposits steady, while loan EMI "
    "burdens for existing borrowers remain the same. KYC norms for opening a "
    "fixed deposit were also simplified."
)

BFSI_HI = (
    "बैंक ने ऋण पर ब्याज दर घटा दी है। बीमा पॉलिसी और प्रीमियम की जानकारी के लिए "
    "अपने खाता विवरण की जाँच करें। निवेश से पहले जमा राशि की शर्तें पढ़ें।"
)

MATH = (
    "Theorem: the sum of the first n odd numbers equals n squared. Proof: we "
    "proceed by induction. Step 1 establishes the base case since 1 = 1. "
    "Therefore the equation 1 + 3 + 5 = 9 = 3*3 holds, and the algorithm follows."
)

HINDI_PROSE = "आज मौसम बहुत अच्छा है और बच्चे बाहर खेल रहे हैं।"
ENGLISH_PROSE = "The weather is lovely today and the children are playing outside in the park."


def test_code_detected():
    assert domain.classify(CODE, "eng") == "coding"


def test_bfsi_english():
    assert domain.classify(BFSI_EN, "eng") == "bfsi"


def test_bfsi_hindi():
    assert domain.classify(BFSI_HI, "hin") == "bfsi"


def test_reasoning():
    assert domain.classify(MATH, "eng") == "reasoning"


def test_indic_prose():
    assert domain.classify(HINDI_PROSE, "hin") == "indic"


def test_general_english():
    assert domain.classify(ENGLISH_PROSE, "eng") == "general"


def test_one_keyword_is_not_bfsi():
    assert domain.classify("I walked past the bank of the river near the bridge.", "eng") == "general"


def test_precedence_code_beats_bfsi():
    mixed = CODE + "\n" + BFSI_EN
    assert domain.classify(mixed, "eng") == "coding"
