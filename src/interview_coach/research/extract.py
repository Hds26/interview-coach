"""Map a job note onto local topics and draft short Chinese practice items.

The note itself is never stored. Skill names come from a fixed list. Stems
come from templates, not from sentences in the note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from interview_coach.assessment.bank import TOPICS, chinese_subject
from interview_coach.models import Question, RubricPoint

MAX_NOTE_CHARS = 20_000
AD_PATTERNS = (
    "加微信",
    "扫码领取",
    "扫码咨询",
    "保过",
    "限时优惠",
    "课程优惠",
    "代投简历",
    "代理招聘",
    "点击领取",
    "免费试听",
    "培训班",
)
_YEAR = re.compile(r"20\d{2}")


@dataclass(frozen=True)
class SkillRule:
    name: str
    topic: str
    needles: tuple[str, ...]


@dataclass(frozen=True)
class SkillHit:
    name: str
    topic: str


# Longer or more specific needles are listed first inside each rule.
RULES: tuple[SkillRule, ...] = (
    SkillRule("redis", "databases", ("redis",)),
    SkillRule("mysql", "databases", ("mysql",)),
    SkillRule("postgres", "databases", ("postgresql", "postgres")),
    SkillRule("sql", "databases", ("sql",)),
    SkillRule("索引", "databases", ("覆盖索引", "索引")),
    SkillRule("事务", "databases", ("mvcc", "事务", "隔离级别")),
    SkillRule("数据库", "databases", ("数据库",)),
    SkillRule("http", "networking", ("https", "http")),
    SkillRule("tcp", "networking", ("tcp", "udp", "quic")),
    SkillRule("dns", "networking", ("dns",)),
    SkillRule("网络", "networking", ("网络协议", "计算机网络", "网络")),
    SkillRule("python", "python", ("python", "django", "fastapi", "flask")),
    SkillRule("gil", "python", ("gil",)),
    SkillRule("kafka", "system_design", ("kafka",)),
    SkillRule("kubernetes", "system_design", ("kubernetes", "k8s")),
    SkillRule("缓存", "system_design", ("缓存", "cache")),
    SkillRule("限流", "system_design", ("限流", "熔断")),
    SkillRule("微服务", "system_design", ("微服务", "分布式")),
    SkillRule("消息队列", "system_design", ("消息队列",)),
    SkillRule("并发", "concurrency", ("并发", "多线程", "线程池")),
    SkillRule("死锁", "concurrency", ("死锁", "互斥锁")),
    SkillRule("哈希", "arrays_hashing", ("hashmap", "hash map", "哈希", "散列表")),
    SkillRule("数组", "arrays_hashing", ("数组",)),
    SkillRule("二叉树", "trees_graphs", ("二叉树", "二叉搜索树")),
    SkillRule("图", "trees_graphs", ("图遍历", "最短路", "拓扑排序")),
    SkillRule("复杂度", "complexity", ("时间复杂度", "空间复杂度", "复杂度")),
)


def strip_ads(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines() or [text]:
        if any(pattern in line for pattern in AD_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept)


def looks_stale(text: str, today_year: int) -> bool:
    """True when the newest year mentioned is more than a year behind."""
    years = [int(year) for year in _YEAR.findall(text)]
    if not years:
        return False
    return max(years) < today_year - 1


def extract_skills(text: str, limit: int = 6) -> list[SkillHit]:
    """Return lexicon hits only. Nothing from the note is copied into the name."""
    if limit < 1:
        return []
    cleaned = strip_ads(text)[:MAX_NOTE_CHARS]
    folded = cleaned.lower()
    found: list[SkillHit] = []
    seen: set[str] = set()
    for rule in RULES:
        if rule.name in seen or rule.topic not in TOPICS:
            continue
        if any(_needle_in(needle, cleaned, folded) for needle in rule.needles):
            seen.add(rule.name)
            found.append(SkillHit(rule.name, rule.topic))
        if len(found) == limit:
            break
    return found


def consistent_skills(groups: list[list[SkillHit]], limit: int = 6) -> list[SkillHit]:
    """Keep a skill only when at least two sources mention it."""
    if len(groups) <= 1:
        return (groups[0] if groups else [])[:limit]
    counts: dict[str, int] = {}
    chosen: dict[str, SkillHit] = {}
    for group in groups:
        for hit in {item.name: item for item in group}.values():
            counts[hit.name] = counts.get(hit.name, 0) + 1
            chosen.setdefault(hit.name, hit)
    ordered = [chosen[name] for name, count in counts.items() if count >= 2]
    return ordered[:limit]


def draft_items(skills: list[SkillHit], limit: int = 5, session_key: str = "0") -> list[Question]:
    """Build at most ``limit`` Chinese items. Stems are templates, not the note."""
    if not skills or limit < 1:
        return []
    cap = min(limit, 5)
    target = min(cap, max(len(skills), min(3, cap)))
    items: list[Question] = []
    cursor = 0
    while len(items) < target:
        skill = skills[cursor % len(skills)]
        variant = len(items)
        items.append(_template(skill, variant, f"rg-{session_key}-{len(items)}"))
        cursor += 1
    return items


def echoes_source(prompt: str, source: str, window: int = 24) -> bool:
    """True when a draft repeats a long stretch of the original note."""
    compact_source = re.sub(r"\s+", "", source)
    compact_prompt = re.sub(r"\s+", "", prompt)
    if len(compact_prompt) < window or len(compact_source) < window:
        return False
    for start in range(0, len(compact_prompt) - window + 1):
        if compact_prompt[start : start + window] in compact_source:
            return True
    return False


def _needle_in(needle: str, original: str, folded: str) -> bool:
    if not needle:
        return False
    if needle.isascii():
        return needle.lower() in folded
    return needle in original


def _template(skill: SkillHit, variant: int, question_id: str) -> Question:
    label = chinese_subject(skill.topic)
    name = skill.name
    if variant % 3 == 2:
        return Question(
            id=question_id,
            topic=skill.topic,
            difficulty=3,
            prompt=f"用一两句话说明，面试里问到{name}时，它和{label}的哪一个权衡最值得先讲。",
            choices=(),
            answer=-1,
            explanation=f"先点明{name}解决的问题，再说代价，不要把题目原文背下来。",
            kind="open",
            tags=("research", skill.topic),
            rubric=(
                RubricPoint("点出这个技能要解决的问题", (name, "问题", "场景")),
                RubricPoint("说出一个代价或边界", ("代价", "权衡", "失效", "过期")),
                RubricPoint("把它放回这个主题", (label, "主题")),
            ),
        )
    if variant % 3 == 1:
        return Question(
            id=question_id,
            topic=skill.topic,
            difficulty=3,
            prompt=f"准备{name}相关的{label}问题时，下面哪件事应该先讲清楚？",
            choices=(
                f"{name}适用的场景，以及它不该被当成银弹的地方",
                "把招聘文案整段背下来",
                "先报一个没有依据的掌握百分比",
                "跳过失败情况，只讲顺利路径",
            ),
            answer=0,
            explanation=f"面试官要听{name}用在什么场景、付出什么代价，而不是一段原文。",
            kind="mcq",
            tags=("research", skill.topic),
        )
    return Question(
        id=question_id,
        topic=skill.topic,
        difficulty=2,
        prompt=f"岗位提到了{name}。它在{label}里更常见的角色是：",
        choices=(
            f"一个可以单独拿出来讲清权衡的{label}知识点",
            "一个必须整段抄进答案的广告",
            "一个还没做题也能叫薄弱项的结论",
            "一个和这个主题无关的口号",
        ),
        answer=0,
        explanation=f"{name}只用来决定接下来多练{label}，不会被当成已经做错的证据。",
        kind="mcq",
        tags=("research", skill.topic),
    )
