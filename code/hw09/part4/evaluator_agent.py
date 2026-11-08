"""HW9 Part 4 - Evaluator Agent: checks an answer against the reference dataset (ground truth).

The verdict is rule-based on purpose: the reference dataset holds the exact facts, so the evaluator
looks up the record the question is about, works out which field is asked, and checks that the answer
states the reference value. (A 3B model as judge approved wrong answers in HW7/HW8.)

Returns {result: PASS|REVISE, explanation, feedback (REVISE only), failure_pattern, expected}.
Failure patterns:
  stale_value          answer gives the first-report value instead of the current verified value
  missing_value        answer does not state the value that was asked for
  unsupported_answer   no reference record exists (unknown incident / off-domain) but the answer gives details
  unnecessary_decline  the record exists but the answer says there is no record
"""
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

INCIDENT_CODE = re.compile(r"\bINC-\d{6}\b", re.IGNORECASE)

FIELD_RULES = [   # (field, question pattern) - checked in this order, several fields may match
    ("current_status", r"\b(status|resolved|cleared|still|dispatched|crew|restored|ongoing)\b"),
    ("current_delay_min", r"\b(delay|how long|minutes|late)\b"),
    ("passengers_affected", r"\bpassengers?\b|\bhow many (riders|people)\b"),
    ("category", r"\b(category|classified|type of incident)\b"),
    ("line", r"\b(which|what) line\b|\bline is\b"),
    ("location", r"\b(where|location)\b"),
    ("cause", r"\b(caused?|why|reason)\b"),
    ("alternative", r"\b(alternatives?|instead|shuttle)\b"),
]
FIELD_LABEL = {"current_status": "current status", "current_delay_min": "current delay (minutes)",
               "passengers_affected": "passengers affected (latest count)", "category": "category",
               "line": "line", "location": "location", "cause": "cause", "alternative": "alternative for riders"}
DECLINE = re.compile(
    r"no record|not (found|listed|available)|(isn't|is not|not) in (the|my|our) (data|records?|dispatch|incident)|"
    r"(don't|do not) have|no (information|data|details)|(cannot|can't|couldn't|could not|unable to) (find|provide|"
    r"answer|help)|outside (of )?(the|my)|only (help|answer)|not related to|no incident", re.IGNORECASE)
NEGATED = r"(not|n't|never|un)\s*(yet\s*)?(been\s*)?$"


@dataclass
class Evaluation:
    """Evaluator Agent message back to the Answering Agent."""
    result: str                                   # PASS | REVISE
    explanation: str
    feedback: Optional[str] = None
    failure_pattern: Optional[str] = None
    expected: dict = field(default_factory=dict)  # field -> reference value
    reference_ids: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-able."""
        return asdict(self)


def has_token(text: str, token: str) -> bool:
    """Case-insensitive whole-word match that is not directly negated ('not resolved' does not count)."""
    for m in re.finditer(r"(?<![\w-])" + re.escape(token.lower()) + r"(?![\w-])", text.lower()):
        if not re.search(NEGATED, text.lower()[max(0, m.start() - 14):m.start()]):
            return True
    return False


class EvaluatorAgent:
    """Ground truth = reference_data.json."""

    def __init__(self, reference_path: Path) -> None:
        self.ref = json.loads(Path(reference_path).read_text(encoding="utf-8"))
        self.incidents = {i["incident_code"]: i for i in self.ref["incidents"]}
        self.status_values = self.ref["status_values"]

    # -- what does the question need? ----------------------------------------------
    @staticmethod
    def fields_asked(question: str) -> list[str]:
        """Fields of the incident record the question asks about."""
        q = question.lower()
        found = [f for f, pat in FIELD_RULES if re.search(pat, q)]
        return found or ["category"]

    def accepted(self, rec: dict, fld: str) -> tuple[str, list[list[str]]]:
        """(display value, alternatives - each a list of tokens that must all appear)."""
        if fld == "current_status":
            v = rec["current_status"]
            return v, [[s] for s in self.status_values[v]]
        if fld in ("current_delay_min", "passengers_affected"):
            return str(rec[fld]), [[str(rec[fld])]]
        if fld == "category":
            return rec["category"], [[rec["category"]]]
        if fld == "line":
            return f"{rec['line_code']} ({rec['line_name']})", [[rec["line_code"]], [rec["line_name"].split(" - ")[0]]]
        if fld == "location":
            return rec["location"], [rec["location_keys"]]
        return rec[fld], [[k] for k in rec[f"{fld}_keys"]]          # cause / alternative: any key term

    def first_report_tokens(self, rec: dict, fld: str) -> list[str]:
        """Values from the first dispatch report that differ from the current value (stale markers)."""
        first = rec["first_report"]
        if fld == "current_status" and first["status"] != rec["current_status"]:
            return self.status_values[first["status"]]
        if fld == "current_delay_min" and first["delay_min"] != rec["current_delay_min"]:
            return [str(first["delay_min"])]
        if fld == "passengers_affected" and first["passengers_affected"] != rec["passengers_affected"]:
            return [str(first["passengers_affected"])]
        if fld == "category" and first["category"] != rec["category"]:
            return [first["category"]]
        return []

    def matching_policy(self, question: str) -> Optional[dict]:
        """Policy record whose match words all appear in the question."""
        q = question.lower()
        for p in self.ref["policies"]:
            if all(w in q for w in p["match_all"]):
                return p
        return None

    # -- the check ----------------------------------------------------------------------
    def evaluate(self, question: str, answer: str) -> Evaluation:  # noqa: PLR0911
        """PASS or REVISE with an explanation and (for REVISE) correction feedback."""
        answer = answer or ""
        declined = bool(DECLINE.search(answer))
        codes = [c.upper() for c in INCIDENT_CODE.findall(question)]
        known = [c for c in codes if c in self.incidents]

        if codes and not known:                                     # unknown incident code
            return self._expect_decline(answer, declined, f"{', '.join(codes)} is not in the reference dataset")
        if not codes:
            policy = self.matching_policy(question)
            if policy is None:                                      # off-domain / no reference fact
                return self._expect_decline(answer, declined, "the question matches no incident or policy "
                                                              "in the reference dataset")
            missing = [t for t in policy["required"] if not has_token(answer, t)]
            if not missing:
                return Evaluation("PASS", f"Follows {policy['policy_id']} ({policy['topic']}): mentions "
                                          f"{', '.join(policy['required'])}.", expected={"policy": policy["text"]},
                                  reference_ids=[policy["policy_id"]])
            return Evaluation("REVISE", f"{policy['policy_id']} requires {', '.join(missing)}; the answer omits it.",
                              feedback=f"Reference policy {policy['policy_id']}: \"{policy['text']}\" "
                                       f"Rewrite the answer so it follows this policy.",
                              failure_pattern="missing_value", expected={"policy": policy["text"]},
                              reference_ids=[policy["policy_id"]])

        rec = self.incidents[known[0]]
        expected, problems, stale_seen = {}, [], []
        for fld in self.fields_asked(question):
            shown, alternatives = self.accepted(rec, fld)
            expected[fld] = shown
            if any(all(has_token(answer, t) for t in alt) for alt in alternatives):
                continue
            stale = [t for t in self.first_report_tokens(rec, fld) if has_token(answer, t)]
            problems.append(fld)
            stale_seen += [(fld, t) for t in stale]
        if not problems:
            return Evaluation("PASS", f"{rec['incident_code']}: " + "; ".join(f"{FIELD_LABEL[f]} = {v}"
                                                                              for f, v in expected.items())
                              + " - matches the reference dataset.", expected=expected,
                              reference_ids=[rec["incident_code"]])
        wanted = "; ".join(f"{FIELD_LABEL[f]} = {expected[f]}" for f in problems)
        if declined:
            pattern = "unnecessary_decline"
            expl = f"{rec['incident_code']} exists in the reference dataset but the answer says there is no record."
        elif stale_seen:
            pattern = "stale_value"
            expl = (f"{rec['incident_code']}: the answer gives the first-report value "
                    f"({', '.join(f'{FIELD_LABEL[f]} {t}' for f, t in stale_seen)}) instead of the current value.")
        else:
            pattern = "missing_value"
            expl = f"{rec['incident_code']}: the answer does not state the {', '.join(FIELD_LABEL[f] for f in problems)}."
        feedback = (f"{expl} The reference dataset (verified, as of {self.ref['as_of']}) says: {wanted}. "
                    f"Answer with these values.")
        return Evaluation("REVISE", expl, feedback=feedback, failure_pattern=pattern, expected=expected,
                          reference_ids=[rec["incident_code"]])

    @staticmethod
    def _expect_decline(answer: str, declined: bool, why: str) -> Evaluation:
        if declined:
            return Evaluation("PASS", f"Correctly says there is no record ({why}).", expected={"no_record": why})
        return Evaluation("REVISE", f"Unsupported answer: {why}, but the answer gives details anyway.",
                          feedback=f"There is no matching record: {why}. Reply in one sentence that there is no "
                                   f"record of this in the s1346 transit incident data, and give no other details.",
                          failure_pattern="unsupported_answer", expected={"no_record": why})
