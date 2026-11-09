"""Template rewrite tips and an optional improved example. No model."""

from __future__ import annotations

from interview_coach.star.bank import StarItem
from interview_coach.star.parse import SECTIONS, section_label
from interview_coach.star.rubric import StarScore

_TIPS = {
    "zh": {
        ("situation", "completeness"): "情境第一句写清项目或系统，不要只说「之前做过一个项目」。",
        ("situation", "specificity"): "补上时间或阶段，以及你当时的角色，例如「上个季度我在支付团队」。",
        ("task", "completeness"): "任务写成你个人要交付的目标，而不是团队口号。",
        ("task", "constraint"): "补一条限制：期限、风险，或你明确不能做什么。",
        ("action", "ownership"): "行动用「我先」开头，写你亲自做的步骤，不要只写「我们讨论了」。",
        ("action", "specificity"): "行动写成两步具体动作，例如对齐差异、加开关、做排查。",
        ("action", "trace"): "补一个可以核对的痕迹：日志、指标、开关或对照表。",
        ("result", "quantified"): "结果给一个前后对比的数字，例如错误率从 12% 降到 0。",
        ("result", "outcome"): "写清业务结果：恢复、上线或延迟下降，而不只是「后来就好了」。",
        ("result", "reflection"): "最后加一句如果重来会改什么，或你学到的一条。",
    },
    "en": {
        ("situation", "completeness"): "Open the situation with the system or project, not “a project I once did”.",
        ("situation", "specificity"): "Add when it happened and your role, for example “last quarter on the payments team”.",
        ("task", "completeness"): "State the outcome you personally had to deliver.",
        ("task", "constraint"): "Add one constraint: a deadline, a risk, or something you could not do.",
        ("action", "ownership"): "Start the action with what you did yourself. “We discussed it” is not enough.",
        ("action", "specificity"): "Name two concrete steps, such as aligning the diff, adding a flag, or debugging.",
        ("action", "trace"): "Add a trace someone could check: a log, a metric, a flag, or a comparison.",
        ("result", "quantified"): "Put a before-and-after number in the result, such as error rate from 12% to 0.",
        ("result", "outcome"): "Name the business outcome: restored, shipped, or latency down, not “it got better”.",
        ("result", "reflection"): "Close with what you would change next time, or one thing you learned.",
    },
}

_FALLBACK = {
    "zh": (
        "情境用一句说清时间、系统和你的角色。",
        "行动只留你亲自做的两步，并带上日志或指标。",
        "结果用前后数字对比，并补一句如果重来会改什么。",
    ),
    "en": (
        "Say when it was, which system, and your role in one sentence.",
        "Keep two steps you did yourself, plus a log or a metric.",
        "Compare a number before and after, then say what you would change.",
    ),
}

_STRONG = {
    "zh": (
        "四段已经齐了。情境再压成一句：时间、系统、你的角色。",
        "行动只留两步你亲自做的事，结果的数字放在第一句。",
    ),
    "en": (
        "The four sections are in place. Tighten the situation to when, which system, and your role.",
        "Keep two steps you did yourself, and put the result number in the first sentence.",
    ),
}


def rewrite_tips(score: StarScore, lang: str) -> tuple[str, ...]:
    """Two or three actionable tips from the missed checks."""
    language = "en" if lang == "en" else "zh"
    table = _TIPS[language]
    chosen: list[str] = []
    for name in SECTIONS:
        for code in score.missed.get(name, ()):
            tip = table.get((name, code))
            if tip and tip not in chosen:
                chosen.append(tip)
            if len(chosen) == 3:
                return tuple(chosen)
    if not chosen and not score.weak:
        return _STRONG[language]
    for tip in _FALLBACK[language]:
        if len(chosen) >= 2:
            break
        if tip not in chosen:
            chosen.append(tip)
    return tuple(chosen[:3])


def example_lines(item: StarItem, lang: str) -> tuple[str, ...]:
    header = "可以改成：" if lang != "en" else "One way to shape it:"
    lines = [header]
    for name, text in zip(SECTIONS, item.example, strict=True):
        label = section_label(name, lang)
        sep = "：" if lang != "en" else ": "
        lines.append(f"{label}{sep}{text}")
    return tuple(lines)
