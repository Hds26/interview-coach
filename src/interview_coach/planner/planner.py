"""Seven-day plans with measurable acceptance criteria.

Policies:
- shrink: reported completion below 60%. Fewer topics, an easier score bar, 5 fewer minutes (floor 10).
- stretch: completion at least 85% and quiz accuracy at least 70%. Harder checks, 5 more minutes (cap 120).
- steady: otherwise. Same minutes, unfinished topics move to the front.

Only lines the session can score are stored. Reflection prompts such as
"write 3 definitions" are not acceptance checks.

After any topic has a missed answer, that topic is scheduled before the
weighted order of everything else. Equal unpracticed topics still break ties
by id, but they are not treated as a diagnosis.
"""

from __future__ import annotations

from interview_coach.assessment.bank import chinese_subject
from interview_coach.assessment.open_items import open_question_for, open_questions_for
from interview_coach.assessment.scoring import is_weak_evidence
from interview_coach.models import DayDraft, Question, TopicScore

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
    """Missed topics first, then everyone else by weighted ability."""
    if not scores:
        raise ValueError("at least one topic score is required")
    table = weights or {}

    def ability_key(item: TopicScore) -> tuple[float, str]:
        weight = table.get(item.topic, 1.0) or 1.0
        return (item.ability / weight, item.topic)

    weak: list[TopicScore] = []
    rest: list[TopicScore] = []
    for item in scores:
        if is_weak_evidence(item.answered, item.correct, item.credit):
            weak.append(item)
        else:
            rest.append(item)
    # Misses jump the queue. Clean and unpracticed topics stay in weighted order,
    # so a high-weight topic is not buried just because it was answered correctly.
    ordered = sorted(weak, key=ability_key) + sorted(rest, key=ability_key)
    return [item.topic for item in ordered]


def build_week(
    scores: list[TopicScore] | tuple[TopicScore, ...],
    daily_minutes: int,
    policy: str = "steady",
    carry: list[str] | tuple[str, ...] | None = None,
    weights: dict[str, float] | None = None,
    open_cursor: dict[str, int] | None = None,
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
    usage = dict(open_cursor or {})

    def opener(topic: str) -> Question | None:
        return _take_open(topic, usage)

    core = [pool[index % len(pool)] for index in range(CORE_DAYS)]
    days = [
        _day(index, focus, daily_minutes, abilities.get(focus, 3.0), intensity, "focus", opener)
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
            opener,
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
            opener,
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
    """Return the scored bar as correct/out-of plus a difficulty word.

    Shrink lowers the bar relative to steady. It must not move 6/10 up to 7/10
    just because the day got shorter.
    """
    if intensity == "foundation":
        return 5, 10, "easy"
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
    opener,
) -> DayDraft:
    label = chinese_subject(focus)
    need, out_of, level = _targets(ability, intensity)
    primary = focus_topics(focus)[0]
    question = opener(primary)
    rubric = _rubric_criterion(focus, question)
    if kind == "review":
        objective = f"混合复习{label}，先看错题再做一组小测验。"
        criteria = (
            f"Score at least {need}/{out_of} on a mixed {level} quiz covering these topics.",
            rubric,
        )
    elif kind == "mock":
        objective = f"限时模拟：{label}。"
        bar_need, bar_out = (need, out_of) if intensity == "foundation" else (8, 10)
        criteria = (
            f"Score at least {bar_need}/{bar_out} on the {level} mock covering {label}.",
            rubric,
        )
    else:
        objective = f"集中补齐{label}，并完成一次计分练习。"
        article = "an" if level[:1] in {"a", "e", "i", "o", "u"} else "a"
        criteria = (
            f"Score at least {need}/{out_of} on {article} {level} {chinese_subject(primary)} check.",
            rubric,
        )
    return DayDraft(day_index, focus, minutes, objective, criteria)


def single_focus_day(
    topic: str,
    minutes: int,
    ability: float,
    open_cursor: dict[str, int] | None = None,
) -> DayDraft:
    """One focus day. Callers use it to nudge a single pending day, not the week."""
    usage = dict(open_cursor or {})
    return _day(1, topic, minutes, ability, "steady", "focus", lambda name: _take_open(name, usage))


def focus_topics(focus: str) -> list[str]:
    if focus.startswith(("review:", "mock:")):
        _, _, rest = focus.partition(":")
        return [part for part in rest.split("+") if part]
    return [focus]


def _take_open(topic: str, usage: dict[str, int]) -> Question | None:
    items = open_questions_for(topic)
    if not items:
        return None
    index = usage.get(topic, 0)
    usage[topic] = index + 1
    return items[index % len(items)]


def _rubric_criterion(focus: str, question: Question | None) -> str:
    primary = focus_topics(focus)[0]
    chosen = question or open_question_for(primary)
    label = chinese_subject(primary)
    if chosen is None:
        return f"Write 1 open answer on {label} and score at least 2/3 on the local rubric."
    total = len(chosen.rubric)
    need = max(1, total - 1) if total > 1 else 1
    return (
        f"Open item {chosen.id}: answer in your own words and hit at least {need}/{total} "
        f"local rubric points (interview-coach assess --topics {primary} --kinds open --questions 1)."
    )
