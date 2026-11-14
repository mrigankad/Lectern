"""Does a headline contain a verb? A small lexicon check, no language model needed."""
from __future__ import annotations

import re

_AUX = {
    "is", "are", "was", "were", "be", "been", "being", "am", "has", "have", "had", "do", "does", "did",
    "will", "would", "can", "could", "should", "must", "may", "might", "shall", "won't", "can't", "isn't",
    "aren't", "doesn't", "don't", "didn't", "wasn't", "weren't", "hasn't", "haven't", "it's", "we're",
    "that's", "there's", "here's", "let's", "we'll", "we've",
}
_IRREGULAR = {
    "grew", "rose", "fell", "went", "came", "made", "took", "gave", "got", "led", "left", "lost", "won",
    "held", "kept", "met", "paid", "ran", "saw", "sold", "sent", "set", "spent", "stood", "told", "built",
    "bought", "brought", "cut", "hit", "put", "beat", "began", "broke", "chose", "drove", "found", "knew",
    "shrank", "sank", "slid", "stuck", "swung", "taught", "thought", "understood", "wrote", "became",
}
_BASE = """
accelerate achieve add address adopt agree align allow answer apply approve ask avoid back beat become begin
bring build buy call capture carry change choose close come commit compete complete connect continue
control convert cost cover create cut decide decline defend define deliver demand depend deserve design
determine develop double drive drop earn enable end ensure exceed expand expect explain face fail fall fit
fix focus follow force fund gain generate get give go grow halve happen help hire hit hold improve include
increase invest join keep know land launch lead learn leave let lift lose make matter mean measure meet
miss move need open outpace outperform own pay perform plan protect prove provide pull push put raise reach
recover reduce remain replace require return reveal rise risk run save scale sell serve set shape share
ship show shrink sign slow solve spend stall start stay stop support take target tell test threaten trail
triple turn unlock use want win work
flow feed report rely replace reward repay retain renew climb jump slip slide stand sit lag
belong combine compare contain count cross deserve differ doubt emerge exist explain link live
match offer pass pick play point prepare prevent promise rank rate reflect relate respond rest
secure see seem sit speak speed split spread stretch suffer suggest surprise survive switch
track trust try wait warn widen narrow tighten strengthen weaken outgrow overtake underpin
""".split()


def _forms(base: str) -> set[str]:
    forms = {base}
    if base.endswith(("s", "x", "ch", "sh")):
        forms.add(base + "es")
    elif base.endswith("y") and base[-2] not in "aeiou":
        forms.add(base[:-1] + "ies")
        forms.add(base[:-1] + "ied")
    else:
        forms.add(base + "s")
    if base.endswith("e"):
        forms.update({base + "d", base[:-1] + "ing"})
    else:
        forms.update({base + "ed", base + "ing"})
        if re.search(r"[^aeiou][aeiou][bdgmnprt]$", base):
            forms.update({base + base[-1] + "ed", base + base[-1] + "ing"})
    return forms


_VERBS: set[str] = set(_AUX) | set(_IRREGULAR)
for _base in _BASE:
    _VERBS |= _forms(_base)

# Words that are in the lexicon but usually nouns at the start of a title ("Plan", "Cost", "Risk").
_NOUNISH = {"plan", "cost", "risk", "focus", "demand", "change", "control", "design", "target", "test",
            "share", "start", "end", "return", "use", "work", "lead", "set", "back", "call", "close", "cover",
            "drop", "fall", "fit", "force", "fund", "gain", "hire", "hold", "land", "launch", "lift", "measure",
            "move", "need", "open", "pay", "pull", "push", "reach", "rise", "run", "scale", "shape", "show",
            "sign", "support", "turn", "win", "answer", "risks", "costs", "plans", "targets", "needs", "returns",
            "changes", "results", "leads", "gains", "measures", "controls", "demands", "tests", "shares",
            "ends", "wins", "funds", "hires", "moves", "runs", "sets", "calls", "covers", "drops", "falls",
            "forces", "lands", "launches", "lifts", "opens", "pulls", "pushes", "scales", "shapes", "shows",
            "signs", "starts", "supports", "turns", "works", "uses", "holds", "closes", "fits", "pays",
            "reaches", "rises", "backs", "answers", "designs", "focuses"}


def has_verb(text: str) -> bool:
    """True when the text reads as a statement rather than a topic label."""
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    if not tokens:
        return False
    strong = [t for t in tokens if t in _VERBS and t not in _NOUNISH]
    if strong:
        return True
    # A noun-like verb counts when it is not the first or the only content word: "Costs fall", "We plan".
    weak = [i for i, t in enumerate(tokens) if t in _NOUNISH]
    return any(i > 0 for i in weak) and len(tokens) >= 3 and _has_subject_before(tokens, weak)


def _has_subject_before(tokens: list[str], weak: list[int]) -> bool:
    fillers = {"the", "a", "an", "of", "and", "for", "to", "in", "on", "our", "your", "&"}
    for index in weak:
        if index == 0:
            continue
        before = [t for t in tokens[:index] if t not in fillers]
        after = tokens[index + 1:]
        if before and after and tokens[index - 1] not in fillers:
            return True
    return False
