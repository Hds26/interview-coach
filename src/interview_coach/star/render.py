"""Terminal text for one STAR session."""

from __future__ import annotations

from interview_coach.star.parse import SECTIONS, section_label
from interview_coach.star.service import StarReport


def render_report(report: StarReport, lang: str) -> str:
    chinese = lang != "en"
    if chinese:
        lines = [
            "行为面试（STAR），大约 15–25 分钟。只练一个故事。",
            "这不是今天的知识练习，也不会改 7 天计划的主题权重。",
            "",
            f"[{' · '.join(report.tags)}] {report.prompt}",
            "",
        ]
    else:
        lines = [
            "STAR practice, about 15–25 minutes. One story.",
            "This is not today's knowledge session, and it does not change the 7-day topic weights.",
            "",
            f"[{' · '.join(report.tags)}] {report.prompt}",
            "",
        ]
    for name in SECTIONS:
        label = section_label(name, lang)
        body = report.sections.get(name, "").strip()
        if chinese:
            lines.append(f"{label}：{body}")
        else:
            lines.append(f"{label}: {body}")
    detail = "，".join(
        f"{section_label(name, lang)} {round(report.scores[name] * 100)}%" for name in SECTIONS
    ) if chinese else ", ".join(
        f"{section_label(name, lang)} {round(report.scores[name] * 100)}%" for name in SECTIONS
    )
    weak = "、".join(section_label(name, lang) for name in report.weak) if chinese else ", ".join(
        section_label(name, lang) for name in report.weak
    )
    lines.append("")
    if chinese:
        lines.append(f"STAR 得分 {round(report.total * 100)}%（{detail}）。")
        lines.append(f"较弱：{weak or '没有'}。")
        lines.append("建议：")
    else:
        lines.append(f"STAR score {round(report.total * 100)}% ({detail}).")
        lines.append(f"Weak: {weak or 'none'}.")
        lines.append("Tips:")
    for tip in report.tips:
        lines.append(f"- {tip}")
    if report.example:
        lines.append("")
        lines.extend(report.example)
    lines.append("已记下这次练习。" if chinese else "Saved this STAR practice.")
    return "\n".join(lines)
