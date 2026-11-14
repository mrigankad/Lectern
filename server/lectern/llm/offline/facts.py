"""Pull the usable facts out of a prompt: the topic, the numbers with their labels, and the ask."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...engine.numbers import Quantity, find_quantities

_UP = {"up", "grew", "rose", "increased", "climbed", "jumped", "gained", "improved", "doubled", "tripled"}
_DOWN = {"down", "fell", "dropped", "declined", "decreased", "shrank", "slipped", "lost"}
_BAD_WHEN_UP = ("churn", "cost", "attrition", "defect", "error", "bug", "complaint", "downtime", "latency",
                "debt", "burn", "incident", "turnover", "delay", "risk", "loss", "expense", "cac", "ticket",
                "outage", "wait", "backlog", "refund", "return rate")
_LEAD = re.compile(r"^(?:and|but|while|although|though|so|yet|also|however|our|the|a|an|we have|we|that|this|"
                   r"with|where|because|since|as)\s+", re.IGNORECASE)
_Q = r"[$€£₹]?\s?\d[\d,]*(?:\.\d+)?\s?(?:thousand|million|billion|bn|mm|[kKmMbB](?![A-Za-z]))?\s?(?:%|pp\b|x\b)?"
_MOVE = r"went|rose|grew|increased|climbed|jumped|fell|dropped|declined|decreased|moved|changed|slipped|improved"
_FROM_TO = re.compile(rf"(?P<label>[^,;:]+?)\s+(?:(?:has|have|had)\s+)?(?:(?P<verb>{_MOVE})\s+)?from\s+"
                      rf"(?P<a>{_Q})\s+to\s+(?P<b>{_Q})", re.IGNORECASE)
_CHANGE = re.compile(rf"(?P<label>[^,;:]+?)\s+(?:(?:is|are|was|were|has|have)\s+)?"
                     rf"(?P<verb>up|down|grew|rose|increased|climbed|jumped|fell|dropped|declined|decreased|"
                     rf"shrank|slipped|improved|gained)\s+(?:by\s+)?(?P<q>{_Q})", re.IGNORECASE)
_LEVEL = re.compile(rf"(?P<label>[^,;:]+?)\s+(?:is|are|was|were|reached|hit|stands at|stood at|sits at|"
                    rf"came in at|of)\s+(?:now\s+|at\s+|about\s+|around\s+)?(?P<q>{_Q})", re.IGNORECASE)
_AMOUNT = re.compile(rf"(?P<q>{_Q})\s+(?:in\s+|of\s+|for\s+)?(?P<label>[A-Za-z][A-Za-z\-]*(?:\s+[A-Za-z][A-Za-z\-]*)"
                     r"{0,3})")
_ASK = re.compile(r"\b(?:need|want|ask(?:ing)?|request(?:ing)?|seeking|looking for|would like|hope|aim)\b"
                  r"(?P<who>.*?)\bto\s+(?P<action>(?:approve|fund|sign off|decide|agree|invest|buy|hire|commit|"
                  r"back|support|greenlight|choose|adopt|renew|expand|launch|prioriti[sz]e|allocate|extend|"
                  r"understand|learn|see|know|believe)\b.*)", re.IGNORECASE)
_STOP = {"the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "at", "by", "with", "our", "we", "i",
         "is", "are", "was", "were", "be", "it", "that", "this", "from", "as", "but", "need", "want", "up",
         "down", "my", "me", "us", "their", "your", "will", "would", "should", "can", "about", "into", "have",
         "has", "had", "went", "deck", "presentation", "slides", "make", "create", "build", "please", "they"}


@dataclass(frozen=True)
class Metric:
    label: str                      # "Monthly logo churn"
    value: str                      # "4.1%" (the current value, as written)
    kind: str                       # change | from_to | level | amount
    direction: str = ""             # up | down | ""
    before: str | None = None       # "2.6%" for from_to
    quantity: Quantity | None = None
    before_quantity: Quantity | None = None

    @property
    def good(self) -> bool | None:
        """Is the movement good news? None when there is no movement."""
        if not self.direction:
            return None
        bad_up = any(word in self.label.lower() for word in _BAD_WHEN_UP)
        return (self.direction == "down") if bad_up else (self.direction == "up")

    @property
    def unit(self) -> str:
        return self.quantity.unit if self.quantity else ""

    def sentence(self) -> str:
        """The metric as a short claim: "Revenue is up 34%"."""
        if self.kind == "from_to" and self.before:
            verb = "rose" if self.direction == "up" else "fell" if self.direction == "down" else "moved"
            return f"{self.label} {verb} from {self.before} to {self.value}"
        if self.kind == "change":
            return f"{self.label} is {self.direction or 'up'} {self.value}"
        if self.kind == "amount":
            return f"{self.value} {self.label[0].lower()}{self.label[1:]}"
        return f"{self.label} is {self.value}"

    def caption(self) -> str:
        if self.kind == "from_to" and self.before:
            return f"{self.label}, {'up' if self.direction == 'up' else 'down'} from {self.before}"
        if self.kind == "change":
            return f"{self.label} {'growth' if self.direction == 'up' else 'decline'}"
        return self.label


@dataclass
class Facts:
    prompt: str
    topic: str
    audience: str
    ask: str | None = None              # "approve a $1.2M retention budget"
    period: str | None = None           # "Q3"
    metrics: list[Metric] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)

    @property
    def good(self) -> list[Metric]:
        return [m for m in self.metrics if m.good is True]

    @property
    def bad(self) -> list[Metric]:
        return [m for m in self.metrics if m.good is False]

    @property
    def amounts(self) -> list[Metric]:
        return [m for m in self.metrics if m.kind == "amount"]

    @property
    def money(self) -> list[Metric]:
        """Amounts of money: what an ask is usually about."""
        return [m for m in self.amounts if m.unit in {"$", "€", "£", "₹"}]

    def money_sentence(self) -> str | None:
        """The prompt's own sentence about the money, when it is short enough to be a headline."""
        for metric in self.money:
            for sentence in self.sentences:
                if metric.value in sentence and 3 <= len(sentence.split()) <= 12:
                    return sentence[:1].upper() + sentence[1:]
            return f"This takes a {metric.sentence()}"
        return None

    @property
    def topic_inline(self) -> str:
        """The topic as it reads mid-sentence: lower-cased unless it starts with a name."""
        if len(self.topic.split()) > 5:
            return "this topic"       # too long to repeat inside a headline
        first = self.topic.split()[0] if self.topic.split() else ""
        common = first.lower() in self.prompt.split() or first.lower() in {"how", "what", "why", "our", "the"}
        return _lower_first(self.topic) if common else self.topic

    @property
    def trend(self) -> Metric | None:
        """The metric with a before and an after: the natural chart."""
        return next((m for m in self.metrics if m.kind == "from_to"), None)

    @property
    def subject(self) -> str:
        """What the bad news is about, for plan wording: "monthly logo churn"."""
        if self.bad:
            return _lower_first(self.bad[0].label)
        return self.topic_inline

    def ask_sentence(self) -> str | None:
        if not self.ask:
            return None
        who = self.audience if self.audience.lower().startswith(("the ", "our ", "you")) else "you"
        return f"We ask {_lower_first(who)} to {self.ask}"


def _lower_first(text: str) -> str:
    if len(text) > 1 and text[1].isupper():
        return text       # acronym such as "ARR"
    return text[:1].lower() + text[1:]


def _clean_label(label: str) -> str:
    label = label.strip(" ,.;:-")
    previous = None
    while previous != label:
        previous = label
        label = _LEAD.sub("", label).strip()
    label = re.sub(r"\s+(?:has|have|is|are|was|were)$", "", label)
    words = label.split()
    if len(words) > 5:
        words = words[-5:]
    label = " ".join(words)
    return label[:1].upper() + label[1:] if label else ""


def _first_quantity(text: str) -> Quantity | None:
    found = find_quantities(text)
    return found[0] if found else None


def _clauses(sentence: str) -> list[str]:
    parts = re.split(r",\s+(?:(?:but|and|while|yet|so)\s+)?|;\s*|\s+but\s+|\s+while\s+|\s+and\s+(?=[A-Za-z ]+\s(?:is|are|"
                     r"was|were|went|rose|fell|grew)\b)", sentence)
    return [p.strip() for p in parts if p and p.strip()]


def extract_metrics(text: str) -> list[Metric]:
    metrics: list[Metric] = []
    seen: set[str] = set()

    def add(metric: Metric) -> None:
        key = f"{metric.label.lower()}|{metric.value}"
        if metric.label and metric.value and key not in seen and len(metrics) < 8:
            seen.add(key)
            metrics.append(metric)

    for sentence in split_sentences(text):
        for clause in _clauses(sentence):
            match = _FROM_TO.search(clause)
            if match:
                a, b = _first_quantity(match.group("a")), _first_quantity(match.group("b"))
                if a and b:
                    direction = "up" if b.value > a.value else "down" if b.value < a.value else ""
                    add(Metric(label=_clean_label(match.group("label")), value=match.group("b").strip(),
                               kind="from_to", direction=direction, before=match.group("a").strip(),
                               quantity=b, before_quantity=a))
                    continue
            match = _CHANGE.search(clause)
            level = _LEVEL.search(clause)
            if match and level and len(level.group("label")) < len(match.group("label")):
                match = None
            if match and _first_quantity(match.group("q")):
                verb = match.group("verb").lower()
                add(Metric(label=_clean_label(match.group("label")), value=match.group("q").strip(), kind="change",
                           direction="up" if verb in _UP else "down", quantity=_first_quantity(match.group("q"))))
                continue
            match = level
            if match and _first_quantity(match.group("q")) and len(_clean_label(match.group("label"))) > 2:
                add(Metric(label=_clean_label(match.group("label")), value=match.group("q").strip(), kind="level",
                           quantity=_first_quantity(match.group("q"))))
                continue
            for match in _AMOUNT.finditer(clause):
                quantity = _first_quantity(match.group("q"))
                words = [w for w in match.group("label").split()]
                while words and words[-1].lower() in _STOP:
                    words.pop()
                while words and words[0].lower() in _STOP:
                    words.pop(0)
                if quantity and (quantity.unit or quantity.value >= 20) and words:
                    label = " ".join(words[:3])
                    add(Metric(label=label[:1].upper() + label[1:], value=match.group("q").strip(), kind="amount",
                               quantity=quantity))
    return metrics


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“$\d])|\n+", text.strip())
    return [p.strip().rstrip(".!?").strip() for p in parts if p and p.strip().rstrip(".!?").strip()]


def _topic(sentences: list[str], prompt: str) -> str:
    first = sentences[0] if sentences else prompt
    first = re.sub(r"^(?:please\s+)?(?:create|make|build|write|draft|prepare|i need|we need|give me)\s+(?:me\s+)?"
                   r"(?:a|an|the)?\s*(?:[\w\-]+\s+){0,2}?(?:deck|presentation|slides|talk)"
                   r"\s*(?:about|on|for|covering|explaining|to)?\s*", "", first, flags=re.IGNORECASE)
    first = re.sub(r"^(?:a|an|the)?\s*(?:[\w\-]+\s+)?(?:deck|presentation|talk)\s+(?:about|on|for|covering)\s+", "",
                   first, flags=re.IGNORECASE)
    first = re.sub(r"^(?:our|my|the|a|an|this is|here is)\s+", "", first, flags=re.IGNORECASE).strip(" .,:;-")
    words = first.split()
    if find_quantities(first) or len(words) > 9:
        clause = re.split(r"[,;:]|\s+(?:is|are|was|were|went|but|because|which|that)\s+", first)[0]
        words = clause.split()[:7]
    topic = " ".join(words).strip(" .,:;-") or "Untitled deck"
    head = topic.split(",")[0].strip()
    if "," in topic and head:
        topic = head          # "Tidal, an AI scheduling tool" -> "Tidal"
    return topic[:1].upper() + topic[1:]


def _keywords(prompt: str, limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for word in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", prompt):
        lower = word.lower()
        if lower not in _STOP:
            counts[lower] = counts.get(lower, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda item: -item[1])][:limit]


def extract(prompt: str, audience: str | None = None, goal: str | None = None) -> Facts:
    sentences = split_sentences(prompt)
    ask = None
    who = ""
    match = next((m for m in (_ASK.search(sentence) for sentence in sentences) if m), None)
    if match:
        ask = match.group("action").strip(" .")
        who = re.sub(r"^\s*(?:for\s+)?", "", match.group("who") or "").strip(" ,")
    elif goal:
        goal_match = re.search(r"\b(?:to\s+)?((?:approve|fund|decide|agree|invest|buy|hire|commit|support|choose|"
                               r"adopt|sign)\b.*)", goal, re.IGNORECASE)
        ask = (goal_match.group(1) if goal_match else goal).strip(" .")
        ask = ask[:1].lower() + ask[1:]
    if not audience:
        audience = who if 0 < len(who.split()) <= 4 else ""
    period = None
    period_match = re.search(r"\b(Q[1-4]|H[12]|FY\s?\d{2,4}|20\d{2})\b", prompt)
    if period_match:
        period = period_match.group(1)
    return Facts(prompt=prompt, topic=_topic(sentences, prompt), audience=audience or "the audience", ask=ask,
                 period=period, metrics=extract_metrics(prompt), keywords=_keywords(prompt), sentences=sentences)


def previous_period(period: str | None) -> tuple[str, str]:
    """Labels for a before/after chart: ("Q2", "Q3"), or ("Before", "Now")."""
    if period:
        match = re.fullmatch(r"Q([1-4])", period)
        if match:
            n = int(match.group(1))
            return (f"Q{n - 1}" if n > 1 else "Q4", period)
        if re.fullmatch(r"20\d{2}", period):
            return str(int(period) - 1), period
    return "Before", "Now"
