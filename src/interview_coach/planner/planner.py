"""Seven-day plans with measurable acceptance criteria.

Policies:
- shrink: reported completion below 60%. Fewer topics, easier checks, 5 fewer minutes (floor 10).
- stretch: completion at least 85% and quiz accuracy at least 70%. Harder checks, 5 more minutes (cap 120).
- steady: otherwise. Same minutes, unfinished topics move to the front.
"""

from __future__ import annotations

from interview_coach.assessment.bank import subject_label
from interview_coach.assessment.open_items import open_question_for
from interview_coach.models import DayDraft, TopicScore

SHRINK_BELOW = 0.60
STRETCH_AT = 0.85
STRETCH_ACCURACY = 0.70
CORE_DAYS = 5


def choose_policy(completion_rate: float, accuracy: float) -> str:
    if completion_rate < SHRINK_BELOW:
        return "shrink"
    if completion_rate >= STRETCH_AT and accuracy >= STRETCH_ACCURACY:
        return "stretch"
    return "steady"


def adjusted_minutes(daily_minutes: int, policy: str) -> int:
    if policy == "shrink":
        return max(10, daily_minutes - 5)
    if policy == "stretch":
        return min(120, daily_minutes + 5)
    return daily_minutes


def explain_policy(policy: str, completion_rate: float, accuracy: float) -> str:
    completion = round(completion_rate * 100)
    quiz = round(accuracy * 100)
    if policy == "shrink":
        return (
            f"completion {completion}% is below 60%; next week narrows to the weakest topics, "
            f"eases the score threshold, and trims 5 minutes when the budget allows "
            f"(recent quiz accuracy {quiz}%)."
        )
    if policy == "stretch":
        return (
            f"completion {completion}% and quiz accuracy {quiz}% clear the stretch bar "
            f"(at least 85% complete and 70% accurate); next week adds 5 minutes and a harder check."
        )
    return (
        f"completion {completion}% with quiz accuracy {quiz}% stays in the steady band; "
        f"next week keeps the same minutes and pulls unfinished topics forward."
    )


def rank_topics(
    scores: list[TopicScore] | tuple[TopicScore, ...],
    weights: dict[str, float] | None = None,
) -> list[str]:
    if not scores:
        raise ValueError("at least one topic score is required")
    table = weights or {}

    def sort_key(item: TopicScore) -> tuple[float, str]:
        weight = table.get(item.topic, 1.0) or 1.0
        return (item.ability / weight, item.topic)

    return [score.topic for score in sorted(scores, key=sort_key)]


def build_week(
    scores: list[TopicScore] | tuple[TopicScore, ...],
    daily_minutes: int,
    policy: str = "steady",
    carry: list[str] | tuple[str, ...] | None = None,
    weights: dict[str, float] | None = None,
) -> list[DayDraft]:
    ranked = rank_topics(scores, weights)
    abilities = {score.topic: score.ability for score in scores}
    intensity = {"shrink": "foundation", "stretch": "stretch"}.get(policy, "steady")
    if policy == "shrink":
        # A short week follows ability, not whichever calendar days were left open.
        pool = ranked[:3]
    else:
        width = 6 if policy == "stretch" else 5
        pool = _pool(ranked, carry or (), width)
    core = [pool[index % len(pool)] for index in range(CORE_DAYS)]
    days = [
        _day(index, focus, daily_minutes, abilities.get(focus, 3.0), intensity, "focus")
        for index, focus in enumerate(core, start=1)
    ]
    review = pool[:2]
    mock = pool[: min(3, len(pool))]
    days.append(
        _day(
            6,
            "review:" + "+".join(review),
            daily_minutes,
            min(abilities.get(topic, 3.0) for topic in review),
            intensity,
            "review",
        )
    )
    days.append(
        _day(
            7,
            "mock:" + "+".join(mock),
            daily_minutes,
            min(abilities.get(topic, 3.0) for topic in mock),
            intensity,
            "mock",
        )
    )
    return days


def _pool(ranked: list[str], carry: list[str] | tuple[str, ...], width: int) -> list[str]:
    ordered: list[str] = []
    for topic in list(carry) + ranked:
        if topic.startswith(("review:", "mock:")):
            continue
        if topic not in ordered:
            ordered.append(topic)
    if not ordered:
        raise ValueError("no topics to plan")
    return ordered[:width]


def _targets(ability: float, intensity: str) -> tuple[int, int, str]:
    if intensity == "foundation":
        return 7, 10, "easy"
    if intensity == "stretch":
        level = "hard" if ability >= 3.2 else "medium"
        return 8, 10, level
    if ability < 2.5:
        return 6, 10, "easy"
    if ability < 3.8:
        return 6, 10, "medium"
    return 7, 10, "hard"


def _day(
    day_index: int,
    focus: str,
    minutes: int,
    ability: float,
    intensity: str,
    kind: str,
) -> DayDraft:
    label = subject_label(focus)
    need, out_of, level = _targets(ability, intensity)
    if kind == "review":
        objective = f"Mixed review of {label}. Redo misses, then a short timed set."
        criteria = (
            f"Spend {minutes} minutes on mixed review ({label}).",
            f"Score at least {need}/{out_of} on a mixed {level} quiz covering these topics.",
            "Write 1 correction sentence for each missed item.",
            _rubric_criterion(focus),
        )
    elif kind == "mock":
        objective = f"Timed mock on {label}, then score it with the rubric."
        criteria = (
            f"Complete a {minutes}-minute closed-book mock on {label}.",
            "Answer 5 prompts. Rubric: correctness, clarity, and tradeoffs, each 0-2. Total at least 8/10.",
            "Write 3 gaps to carry into the next plan.",
            _rubric_criterion(focus),
        )
    else:
        objective = f"Close gaps in {label} with one focused block and a scored check."
        article = "an" if level[:1] in {"a", "e", "i", "o", "u"} else "a"
        criteria = (
            f"Spend {minutes} focused minutes on {label} in a single sitting.",
            f"Score at least {need}/{out_of} on {article} {level} {label} check.",
            f"Write 3 accurate definitions and 1 worked example for {label}.",
            _rubric_criterion(focus),
        )
    return DayDraft(day_index, focus, minutes, objective, criteria)


def _focus_topics(focus: str) -> list[str]:
    if focus.startswith(("review:", "mock:")):
        _, _, rest = focus.partition(":")
        return [part for part in rest.split("+") if part]
    return [focus]


def _rubric_criterion(focus: str) -> str:
    primary = _focus_topics(focus)[0]
    question = open_question_for(primary)
    label = subject_label(primary)
    if question is None:
        return f"Write 1 open answer on {label} and score at least 2/3 on the local rubric."
    total = len(question.rubric)
    need = max(1, total - 1) if total > 1 else 1
    return (
        f"Open item {question.id}: answer in your own words and hit at least {need}/{total} "
        f"local rubric points (interview-coach assess --topics {primary} --kinds open --questions 1)."
    )
