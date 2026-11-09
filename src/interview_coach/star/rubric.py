"""Local STAR rubric. No model.

Each section scores 0–1 from fixed checks. The total is the equal-weight
mean of the four sections. Keywords use the same token rules as open items,
so ``log`` does not match inside ``catalog``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from interview_coach.assessment.rubric import keyword_hit
from interview_coach.star.parse import SECTIONS

# Below this, a section is called weak. 2/3 of the action or result checks
# is still a rewrite, not a finished section.
WEAK_BELOW = 0.75
WEIGHTS = {name: 0.25 for name in SECTIONS}

_NUMBER = re.compile(r"\d")


@dataclass(frozen=True)
class Check:
    code: str
    keywords: tuple[str, ...] = ()
    quantity: bool = False


CHECKS: dict[str, tuple[Check, ...]] = {
    "situation": (
        Check(
            "completeness",
            ("项目", "系统", "服务", "团队", "客户", "业务", "上线", "事故", "发布", "project", "system", "team", "service", "outage", "release"),
        ),
        Check(
            "specificity",
            ("季度", "迭代", "周", "月", "当时", "我在", "值班", "sprint", "quarter", "week", "month", "deadline"),
        ),
    ),
    "task": (
        Check(
            "completeness",
            ("目标", "负责", "需要", "任务", "要在", "goal", "needed", "responsible"),
        ),
        Check(
            "constraint",
            ("不能", "必须", "风险", "之前", "之内", "constraint", "before", "within", "deadline"),
        ),
    ),
    "action": (
        Check(
            "ownership",
            ("我先", "我把", "我去", "我写", "我做", "我负责", "亲自", "i", "myself"),
        ),
        Check(
            "specificity",
            ("实现", "对齐", "排查", "协调", "设计", "推动", "压测", "回滚", "implemented", "coordinated", "debugged", "designed", "wrote"),
        ),
        Check(
            "trace",
            ("log", "日志", "指标", "开关", "对照", "metric", "metrics"),
        ),
    ),
    "result": (
        Check("quantified", quantity=True),
        Check(
            "outcome",
            ("下降", "提升", "减少", "增加", "完成", "上线", "恢复", "降", "reduced", "increased", "shipped", "latency", "延迟", "错误"),
        ),
        Check(
            "reflection",
            ("如果", "下次", "学到", "反思", "复盘", "learned", "next time", "would"),
        ),
    ),
}


@dataclass(frozen=True)
class StarScore:
    sections: dict[str, float]
    total: float
    weak: tuple[str, ...]
    missed: dict[str, tuple[str, ...]]


def score_sections(sections: dict[str, str]) -> StarScore:
    per: dict[str, float] = {}
    missed: dict[str, tuple[str, ...]] = {}
    for name in SECTIONS:
        score, miss = _section_score(name, sections.get(name, ""))
        per[name] = score
        missed[name] = miss
    total = sum(WEIGHTS[name] * per[name] for name in SECTIONS)
    total = min(1.0, max(0.0, total))
    weak = tuple(name for name in SECTIONS if per[name] < WEAK_BELOW)
    return StarScore(per, total, weak, missed)


def _section_score(name: str, text: str) -> tuple[float, tuple[str, ...]]:
    checks = CHECKS[name]
    body = text.strip()
    if not body:
        return 0.0, tuple(check.code for check in checks)
    missed: list[str] = []
    hits = 0
    for check in checks:
        if _check_hit(check, body):
            hits += 1
        else:
            missed.append(check.code)
    score = hits / len(checks)
    if score < 0 or score > 1:
        raise ValueError("section score must stay between 0 and 1")
    return score, tuple(missed)


def _check_hit(check: Check, text: str) -> bool:
    if check.quantity:
        return _has_quantity(text)
    return any(keyword_hit(text, word) for word in check.keywords)


def _has_quantity(text: str) -> bool:
    if _NUMBER.search(text):
        return True
    return any(keyword_hit(text, word) for word in ("百分之", "percent", "百分比"))
