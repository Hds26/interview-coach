"""Command line for the interview study coach."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from interview_coach import __version__
from interview_coach.app import CoachApp, NothingDue, overall_mastery
from interview_coach.assessment.bank import TOPICS, QuestionBank, display_topic
from interview_coach.assessment.scoring import confidence_percent, mastery_percent
from interview_coach.assessment.targets import TARGETS, target_label, weight_summary
from interview_coach.coach_text import no_profile_text, normalize_lang, plain_topic
from interview_coach.db import Database
from interview_coach.demo import run_demo
from interview_coach.research.search import SearchUnavailable
from interview_coach.research.service import PASTE_HINT, render_preview
from interview_coach.star.parse import read_sections, split_answer_blob
from interview_coach.star.render import render_report
from interview_coach.paths import default_db_path
from interview_coach.profile.service import LEVELS


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "db"):
        args.db = None
    if not hasattr(args, "llm"):
        args.llm = "offline"
    if getattr(args, "command", None) is None:
        args.command = "today"
        args.questions = 5
        args.answers = ""
        args.on = ""
        args.handler = cmd_today
    try:
        return args.handler(args)
    except (LookupError, ValueError, RuntimeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _shared_flags() -> argparse.ArgumentParser:
    """Flags accepted before or after the subcommand. SUPPRESS keeps a leading value."""
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--db", type=Path, default=argparse.SUPPRESS, help="SQLite path (default: data/coach.sqlite)")
    shared.add_argument(
        "--llm",
        choices=("offline", "openai", "deepseek"),
        default=argparse.SUPPRESS,
        help="coach model. offline needs no API key (default); deepseek reads DEEPSEEK_API_KEY",
    )
    shared.add_argument(
        "--lang",
        choices=("zh", "en"),
        default=argparse.SUPPRESS,
        help="coach language. today and ask default to zh",
    )
    return shared


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_flags()
    parser = argparse.ArgumentParser(
        prog="interview-coach",
        description="Offline interview coach. Run interview-coach today for one daily session.",
        parents=[shared],
    )
    parser.add_argument("--version", action="version", version=f"interview-coach {__version__}")
    sub = parser.add_subparsers(dest="command", required=False)

    _today_parser(sub, "today", "do today's practice, then log it when the checks pass")
    _today_parser(sub, "go", "same as today")

    start = sub.add_parser(
        "start",
        parents=[shared],
        help="answer a few questions, save a learner model, and build the 7-day plan",
    )
    start.add_argument("--name", default=None)
    start.add_argument("--role", default=None, help="job title, for example 后端")
    start.add_argument("--daily-minutes", type=int, default=None)
    start.add_argument("--kinds", default=None, help="mcq, open, mcq,open, 选择题, 开放题, or 都要")
    start.add_argument(
        "--weak",
        default=None,
        help="self-rated weak topics, comma-separated. Does not write scores",
    )
    start.add_argument("--paste-jd", action="store_true", help="read a JD from stdin; the note is not stored")
    start.add_argument("--paste-resume", action="store_true", help="read a resume from stdin; the note is not stored")
    start.add_argument("--paste-notes", action="store_true", help="read notes from stdin; the note is not stored")
    start.add_argument("--jd-file", type=Path, default=None, help="local JD file")
    start.add_argument("--resume-file", type=Path, default=None, help="local resume file")
    start.add_argument("--notes-file", type=Path, default=None, help="local notes file")
    start.add_argument("--on", default="", help="YYYY-MM-DD for the plan start when a new week is created")
    start.set_defaults(handler=cmd_start)

    demo = sub.add_parser("demo", parents=[shared], help="run a scripted week and print the report")
    demo.add_argument("--yes", action="store_true", help="delete an existing database without asking")
    demo.set_defaults(handler=cmd_demo)

    profile = sub.add_parser("profile", parents=[shared], help="create or show the learner profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    init = profile_sub.add_parser("init", parents=[shared], help="create or replace the profile")
    init.add_argument("--name", required=True)
    init.add_argument("--role", required=True, help="job title, for example 'Backend engineer' or 后端")
    init.add_argument("--level", choices=LEVELS, default=None)
    init.add_argument("--daily-minutes", type=int, default=None)
    init.add_argument(
        "--target",
        default=None,
        help="skill-weight preset, or auto. Omit to infer from the job title on first init, or to keep the saved target later",
    )
    init.add_argument("--streak-goal", type=int, default=None, help="optional streak target, 0-30 (default 5)")
    init.add_argument("--kinds", default=None, help="preferred items: mcq, open, or mcq,open")
    init.add_argument("--reset", action="store_true", help="reset ability scores; the plan stays")
    init.set_defaults(handler=cmd_profile_init)
    show = profile_sub.add_parser("show", parents=[shared], help="print the profile")
    show.set_defaults(handler=cmd_profile_show)

    assess = sub.add_parser("assess", parents=[shared], help="run an adaptive check (multiple choice and open)")
    assess.add_argument("--questions", type=int, default=12)
    assess.add_argument("--topics", default="", help="comma-separated topic ids")
    assess.add_argument("--kinds", default="mcq,open", help="mcq, open, or both")
    assess.add_argument("--tags", default="", help="comma-separated tags; a question matches any tag")
    assess.add_argument(
        "--answers",
        default="",
        help="comma-separated letters, 0-based indexes, or |open text|",
    )
    assess.set_defaults(handler=cmd_assess)

    drill = sub.add_parser("drill", parents=[shared], help="practice due topics without replacing the week")
    drill.add_argument("--questions", type=int, default=4)
    drill.add_argument("--kinds", default="mcq,open")
    drill.add_argument("--tags", default="")
    drill.add_argument("--answers", default="")
    drill.add_argument("--on", default="", help="YYYY-MM-DD used to decide which topics are due")
    drill.set_defaults(handler=cmd_drill)

    plan = sub.add_parser("plan", parents=[shared], help="build a 7-day plan from current scores")
    plan.add_argument("--start", default="", help="YYYY-MM-DD (default: today)")
    plan.add_argument("--force", action="store_true", help="replace the active plan")
    plan.set_defaults(handler=cmd_plan)

    progress = sub.add_parser("progress", parents=[shared], help="show completion and quiz accuracy")
    progress.set_defaults(handler=cmd_progress)

    log = sub.add_parser("log", parents=[shared], help="record one plan day")
    log.add_argument("--day", type=int, required=True)
    log.add_argument("--minutes", type=int, required=True)
    log.add_argument("--missed", action="store_true")
    log.add_argument("--quiz", default="", help="score as correct/total, for example 6/10")
    log.add_argument("--notes", default="")
    log.set_defaults(handler=cmd_log)

    replan = sub.add_parser("replan", parents=[shared], help="build the next week from completion rate")
    replan.add_argument("--start", default="")
    replan.set_defaults(handler=cmd_replan)

    ask = sub.add_parser("ask", parents=[shared], help="ask the coach; uses local tools")
    ask.add_argument("question", nargs="+")
    ask.set_defaults(handler=cmd_ask)

    topics = sub.add_parser("topics", parents=[shared], help="list topic ids and tags")
    topics.set_defaults(handler=cmd_topics)

    targets = sub.add_parser("targets", parents=[shared], help="list job-target presets and skill weights")
    targets.set_defaults(handler=cmd_targets)

    due = sub.add_parser("due", parents=[shared], help="list topics due for spaced review")
    due.add_argument("--on", default="", help="YYYY-MM-DD (default: today)")
    due.set_defaults(handler=cmd_due)

    export_cmd = sub.add_parser("export", parents=[shared], help="export the active week as Markdown or ICS")
    export_cmd.add_argument("--format", dest="export_format", choices=("md", "ics", "both"), default="md")
    export_cmd.add_argument("--out", default="", help="file path; with both, a path stem or either suffix")
    export_cmd.set_defaults(handler=cmd_export)

    import_cmd = sub.add_parser("import", parents=[shared], help="import practice from local JSON or CSV")
    import_cmd.add_argument("file", type=Path)
    import_cmd.set_defaults(handler=cmd_import)

    research = sub.add_parser(
        "research",
        parents=[shared],
        help="optional company or role targeting (not part of today)",
        description=(
            "Optional. Not part of interview-coach today. "
            "Shows a preview and writes only after you confirm. 不是每天必做。"
        ),
    )
    research.add_argument("query", nargs="*", help="company or role; omit this and pass --paste to stay offline")
    research.add_argument("--paste", action="store_true", help="read a JD or notes from stdin; the note is not stored")
    research.add_argument("--show", action="store_true", help="list accepted research")
    research.add_argument("--clear", nargs="?", const="all", default=None, help="delete one session id, or all")
    research.add_argument("--max-skills", type=int, default=6)
    research.add_argument("--max-items", type=int, default=5)
    research.add_argument("--yes", action="store_true", help="accept the preview without asking (tests and scripts)")
    research.add_argument("--on", default="", help="YYYY-MM-DD used as the bias start")
    research.set_defaults(handler=cmd_research)

    _star_parser(sub, "star", "optional STAR practice; not part of today")
    _star_parser(sub, "behavioral", "alias of star")
    return parser


def _star_parser(sub: argparse._SubParsersAction, name: str, help_text: str) -> argparse.ArgumentParser:
    command = sub.add_parser(name, parents=[_shared_flags()], help=help_text)
    command.add_argument(
        "--answers",
        default="",
        help="one paste (headings or blank lines), or four sections separated by ||",
    )
    command.add_argument("--item", default="", help="STAR item id; omit to draw one")
    command.add_argument("--seed", type=int, default=None, help="draw seed when --item is omitted")
    command.set_defaults(handler=cmd_star)
    return command


def _today_parser(sub: argparse._SubParsersAction, name: str, help_text: str) -> argparse.ArgumentParser:
    command = sub.add_parser(name, parents=[_shared_flags()], help=help_text)
    command.add_argument("--questions", type=int, default=5, help="items in today's session (default 5)")
    command.add_argument("--answers", default="", help="scripted answers, same form as assess")
    command.add_argument("--on", default="", help="YYYY-MM-DD (default: today)")
    command.add_argument("--kinds", default=None, help="mcq, open, or mcq,open for this session")
    command.set_defaults(handler=cmd_today)
    return command


def cmd_demo(args: argparse.Namespace) -> int:
    path = args.db or (Path.cwd() / "data" / "demo.sqlite")
    return run_demo(path, yes=bool(getattr(args, "yes", False)))


def cmd_start(args: argparse.Namespace) -> int:
    pastes, weak, name, role, minutes, kinds = _start_inputs(args)
    app = _app(args)
    if app.db.get_profile() is None and (not name or not role):
        print(no_profile_text("zh"))
        return 1
    result = app.start_onboarding(
        name=name,
        role=role,
        daily_minutes=minutes,
        kinds=kinds,
        weak=weak,
        pastes=pastes,
        on=_parse_date(args.on),
        llm=args.llm,
    )
    print(result.summary)
    return 0


def _start_inputs(args: argparse.Namespace):
    paste_flags = [flag for flag in ("paste_jd", "paste_resume", "paste_notes") if getattr(args, flag)]
    if len(paste_flags) > 1:
        raise ValueError("paste only one of resume, jd, or notes from stdin")
    files = {
        "jd": args.jd_file,
        "resume": args.resume_file,
        "notes": args.notes_file,
    }
    if paste_flags:
        kind = paste_flags[0].removeprefix("paste_")
        if files[kind] is not None:
            raise ValueError(f"pass either --{paste_flags[0].replace('_', '-')} or --{kind}-file")
    pastes: list[tuple[str, str]] = []
    for kind, path in files.items():
        if path is not None:
            pastes.append((kind, Path(path).read_text(encoding="utf-8")))
    if paste_flags:
        pastes.append((paste_flags[0].removeprefix("paste_"), _read_paste()))
    name = args.name
    role = args.role
    minutes = args.daily_minutes
    kinds = args.kinds
    weak = args.weak
    bare = (
        name is None
        and role is None
        and minutes is None
        and kinds is None
        and weak is None
        and not pastes
    )
    if bare and _missing_profile(args) and sys.stdin.isatty():
        name, role, minutes, kinds, weak = _prompt_start()
    return pastes, weak, name, role, minutes, kinds


def _missing_profile(args: argparse.Namespace) -> bool:
    return _app(args).db.get_profile() is None


def _prompt_start() -> tuple[str, str, int | None, str | None, str | None]:
    print("用几件事排好 7 天。直接回车表示用默认。原文不会保存。")
    name = input("名字：").strip()
    role = input("目标职位：").strip()
    minutes_raw = input("每天几分钟（回车 = 30）：").strip()
    style_raw = input("练习方式：1 选择题  2 开放题  3 都要（回车 = 3）：").strip()
    weak_raw = input("觉得弱的主题，可空（例如 数据库,网络）：").strip()
    minutes = int(minutes_raw) if minutes_raw else None
    kinds = style_raw or None
    weak = weak_raw
    return name, role, minutes, kinds, weak


def cmd_profile_init(args: argparse.Namespace) -> int:
    profile = _app(args).init_profile(
        args.name,
        args.role,
        args.level,
        args.daily_minutes,
        args.target,
        streak_goal=args.streak_goal,
        preferred_kinds=args.kinds,
        reset_scores=args.reset,
    )
    print(
        f"Saved {profile.name} ({profile.target_role}, {profile.level}), "
        f"{profile.daily_minutes} min/day, target {profile.target_id}."
    )
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    app = _app(args)
    profile = app.require_profile()
    print(f"name: {profile.name}")
    print(f"role: {profile.target_role}")
    print(f"target: {profile.target_id} ({target_label(profile.target_id)})")
    print(f"weights: {weight_summary(profile.target_id)}")
    print(f"level: {profile.level}")
    print(f"daily_minutes: {profile.daily_minutes}")
    print(f"streak_goal: {profile.streak_goal}")
    print(f"preferred_kinds: {profile.preferred_kinds}")
    model = app.db.get_learner()
    if model is not None:
        print(f"self_weak: {', '.join(model.self_weak) if model.self_weak else '-'}")
        parts = []
        for kind in ("resume", "jd", "notes"):
            topics = model.topics(kind)
            if topics:
                parts.append(kind + "=" + "+".join(topics))
        print(f"source_topics: {', '.join(parts) if parts else '-'}")
    return 0


def cmd_assess(args: argparse.Namespace) -> int:
    app = _app(args)
    topics = _split_csv(args.topics)
    kinds = _split_csv(args.kinds)
    tags = _split_csv(args.tags)
    answers = _parse_answers(args.answers) if args.answers else None
    lang = _lang(args, "zh")
    result = _run_session(
        app.assess, args.questions, topics, kinds, tags, answers, on=None, lang=lang
    )
    return _print_assessment(result, lang)


def cmd_drill(args: argparse.Namespace) -> int:
    app = _app(args)
    if not app.due_topics(_parse_date(args.on)):
        print("No topics are due. The schedule was left unchanged.")
        return 0
    kinds = _split_csv(args.kinds)
    tags = _split_csv(args.tags)
    answers = _parse_answers(args.answers) if args.answers else None
    lang = _lang(args, "zh")
    try:
        result = _run_session(
            lambda count, _topics, choose, kinds, tags, on, on_scored: app.drill(
                count, choose, kinds, tags, on, on_scored
            ),
            args.questions,
            None,
            kinds,
            tags,
            answers,
            on=_parse_date(args.on),
            lang=lang,
        )
    except NothingDue:
        print("No topics are due. The schedule was left unchanged.")
        return 0
    return _print_assessment(result, lang)


def cmd_today(args: argparse.Namespace) -> int:
    app = _app(args)
    lang = _lang(args, "zh")
    try:
        setup = app.prepare_today(
            on=_parse_date(args.on),
            lang=lang,
            kinds=_split_csv(args.kinds) if getattr(args, "kinds", None) else None,
        )
    except LookupError:
        print(no_profile_text(lang))
        return 1
    for line in setup.lines:
        print(line)
    answers = _parse_answers(args.answers) if args.answers else None
    result = _run_session(
        lambda count, topics, choose, kinds, tags, on, on_scored: app.assess(
            count,
            topics,
            choose,
            kinds=kinds,
            tags=tags,
            on=on,
            on_scored=on_scored,
            must_ask=setup.must_ask,
        ),
        args.questions,
        setup.topics,
        setup.kinds,
        None,
        answers,
        on=_parse_date(args.on),
        lang=lang,
    )
    correct = result.correct_count
    print()
    if lang == "zh":
        print(f"这次练了 {len(result.answers)} 题，完全答对 {correct} 题。")
    else:
        print(f"Practiced {len(result.answers)} items, {correct} fully correct.")
    for line in app.closing_lines(result, lang, on=_parse_date(args.on)):
        print(line)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    plan = _app(args).create_plan(start=_parse_date(args.start), force=args.force)
    _print_plan(plan)
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    app = _app(args)
    progress = app.progress()
    print(f"plan: v{progress.version}")
    print(f"done: {progress.days_done}  missed: {progress.days_missed}  pending: {progress.days_pending}")
    print(f"reported_completion: {round(progress.reported_completion * 100)}%")
    print(f"quiz_accuracy: {round(progress.quiz_accuracy * 100)}%")
    print(f"minutes_spent: {progress.minutes_spent}")
    print(f"streak: {app.current_streak()}")
    overdue = app.overdue_count()
    if overdue:
        print(f"overdue: {overdue}")
    print("topics:")
    shown = False
    for score in sorted(app.db.list_scores(), key=lambda item: (item.ability, item.topic)):
        if score.answered == 0:
            continue
        shown = True
        review = score.next_review or "-"
        print(
            f"  {display_topic(score.topic):22} mastery {mastery_percent(score.ability):3d}%  "
            f"confidence {confidence_percent(score.information):3d}%  next_review {review}"
        )
    if not shown:
        print("  (no answered topics)")
    star = app.db.latest_star_summary()
    if star is not None:
        weak = ", ".join(star["weak_sections"]) or "-"
        print(f"star: {round(star['total'] * 100)}%  weak: {weak}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    correct, total = _parse_quiz(args.quiz)
    _app(args).log_day(
        args.day,
        args.minutes,
        completed=not args.missed,
        quiz_correct=correct,
        quiz_total=total,
        notes=args.notes,
    )
    state = "missed" if args.missed else "done"
    print(f"Logged day {args.day} as {state}, {args.minutes} minutes.")
    return 0


def cmd_replan(args: argparse.Namespace) -> int:
    plan, reason = _app(args).replan(start=_parse_date(args.start))
    print(f"policy: {plan.policy}")
    print(f"reason: {reason}")
    _print_plan(plan)
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    app = _app(args)
    print(app.agent(args.llm, lang=_lang(args, "zh")).ask(" ".join(args.question)))
    return 0


def cmd_topics(_: argparse.Namespace) -> int:
    bank = QuestionBank()
    for topic, label in TOPICS.items():
        print(f"{topic:16} {label}")
        print(f"  tags: {', '.join(bank.tags_for(topic))}")
    return 0


def cmd_targets(_: argparse.Namespace) -> int:
    for target_id, spec in TARGETS.items():
        weights = ", ".join(f"{topic}={weight:g}" for topic, weight in sorted(spec.weights.items()))
        print(f"{target_id:22} {spec.label}")
        print(f"  {spec.description}")
        print(f"  {weights}")
    return 0


def cmd_due(args: argparse.Namespace) -> int:
    scores = _app(args).due_topics(_parse_date(args.on))
    if not scores:
        print("No topics are due.")
        return 0
    for score in sorted(scores, key=lambda item: (item.next_review or "", item.ability, item.topic)):
        print(
            f"{score.topic:16} ability={score.ability:.2f}  "
            f"confidence={confidence_percent(score.information):3d}%  next_review={score.next_review}"
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    app = _app(args)
    if args.export_format == "both":
        if not args.out:
            raise ValueError("export --format both needs --out")
        markdown_path, calendar_path = _export_paths(args.out)
        _write_export(markdown_path, app.export_plan("md"))
        _write_export(calendar_path, app.export_plan("ics"))
        print(f"Wrote {markdown_path}")
        print(f"Wrote {calendar_path}")
        return 0
    text = app.export_plan(args.export_format)
    if args.out:
        path = _write_export(Path(args.out), text)
        print(f"Wrote {path}")
        return 0
    print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    app = _app(args)
    if args.show:
        return _research_show(app)
    if args.clear is not None:
        return _research_clear(app, args.clear)
    if args.max_items < 1 or args.max_items > 5:
        raise ValueError("max items must be from 1 to 5")
    if args.max_skills < 1 or args.max_skills > 12:
        raise ValueError("max skills must be from 1 to 12")
    on = _parse_date(args.on)
    if args.paste:
        preview = app.preview_paste(
            _read_paste(),
            label=" ".join(args.query) or "paste",
            max_skills=args.max_skills,
            max_items=args.max_items,
            on=on,
            llm=args.llm,
        )
    elif args.query:
        try:
            preview = app.preview_query(
                " ".join(args.query),
                max_skills=args.max_skills,
                max_items=args.max_items,
                on=on,
            )
        except SearchUnavailable:
            print(PASTE_HINT)
            return 0
    else:
        raise ValueError("pass a query or --paste. research is optional and is not part of today")
    print(render_preview(preview))
    if not preview.skills or not preview.items:
        if not args.paste:
            print(PASTE_HINT)
        return 0
    if not args.yes and not _confirm_research():
        print("未确认，没有写入。计划没有变化。")
        return 0
    session_id = app.accept_research(preview, on=on)
    print(f"已写入研究 {session_id}。今天的命令仍然是 interview-coach today。")
    return 0


def _research_show(app: CoachApp) -> int:
    sessions = app.db.research_sessions()
    if not sessions:
        print("还没有已确认的研究。")
        return 0
    for session in sessions:
        detail = app.db.research_detail(int(session["id"]))
        if detail is None:
            continue
        print(f"#{detail['id']}  {detail['label']}")
        for source in detail["sources"]:
            suffix = f"  {source['url']}" if source["url"] else ""
            print(f"  source: {source['title']}{suffix}")
        for skill in detail["skills"]:
            print(f"  skill: {skill['name']} → {skill['topic']}")
        print(f"  items: {len(detail['items'])}  origin=research_generated")
    return 0


def _research_clear(app: CoachApp, raw: str) -> int:
    if raw == "all":
        removed = app.db.clear_research(None)
    else:
        removed = app.db.clear_research(int(raw))
    print(f"已清除 {removed} 条研究。")
    return 0


def _read_paste() -> str:
    if sys.stdin.isatty():
        print("贴上笔记，单独一行输入 . 结束。原文不会被保存。")
        lines: list[str] = []
        while True:
            line = input()
            if line.strip() == ".":
                break
            lines.append(line)
        return "\n".join(lines)
    return sys.stdin.read()


def _confirm_research() -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        answer = input().strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes", "是"}


def cmd_star(args: argparse.Namespace) -> int:
    app = _app(args)
    lang = _lang(args, "zh")
    if app.db.get_profile() is None:
        print(no_profile_text(lang))
        return 1
    if args.answers:
        sections = split_answer_blob(args.answers)
    elif not sys.stdin.isatty():
        raise RuntimeError("pass --answers when stdin is not a terminal")
    else:
        sections = read_sections(lang, input)
    report = app.practice_star(
        sections,
        item_id=args.item or None,
        seed=args.seed,
        llm=getattr(args, "llm", "offline"),
        lang=lang,
    )
    print(render_report(report, lang))
    if report.llm_error:
        print(f"error: {report.llm_error}", file=sys.stderr)
        return 1
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    result = _app(args).import_progress(args.file)
    print(f"Imported {result.practice_count} practice rows and {result.log_count} log rows.")
    return 0


def _app(args: argparse.Namespace) -> CoachApp:
    return CoachApp(Database(args.db or default_db_path()))


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def _split_csv(raw: str) -> list[str] | None:
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or None


def _run_session(runner, count, topics, kinds, tags, answers, on, lang: str = "en"):
    if answers is None and not sys.stdin.isatty():
        raise RuntimeError("pass --answers when stdin is not a terminal")
    chinese = lang == "zh"

    def choose(question):
        _print_question(question, lang)
        if answers is None:
            if question.kind == "open":
                return _read_open(lang)
            return _read_choice(len(question.choices), lang)
        if choose.cursor >= len(answers):
            raise RuntimeError("not enough --answers for the requested questions")
        choice = answers[choose.cursor]
        choose.cursor += 1
        if question.kind == "open":
            text = choice if isinstance(choice, str) else str(choice)
            prefix = "你的回答" if chinese else "Your answer"
            print(f"{prefix}: {text}")
            return text
        if isinstance(choice, str):
            raise ValueError("multiple-choice answers must be a letter or an index")
        if choice < 0 or choice >= len(question.choices):
            raise ValueError("answer index is out of range")
        prefix = "你的回答" if chinese else "Your answer"
        print(f"{prefix}: {chr(ord('A') + choice)}")
        return choice

    def on_scored(question, scored) -> None:
        if scored.kind == "open":
            hits = ", ".join(scored.rubric_hits) if scored.rubric_hits else ("无" if chinese else "none")
            if chinese:
                print(f"要点得分：{round(scored.score * 100)}%（命中：{hits}）")
            else:
                print(f"Rubric score: {round(scored.score * 100)}% (hit: {hits})")
        elif chinese:
            print("答对了。" if scored.correct else "没对。")
        else:
            print("Correct." if scored.correct else "Not correct.")
        if not scored.correct and question.explanation:
            label = "说明" if chinese else "Explanation"
            print(f"{label}: {question.explanation}")
            if question.kind == "mcq" and 0 <= question.answer < len(question.choices):
                letter = chr(ord("A") + question.answer)
                answer_label = "参考答案" if chinese else "Answer"
                print(f"{answer_label}: {letter}. {question.choices[question.answer]}")

    choose.cursor = 0  # type: ignore[attr-defined]
    return runner(count, topics, choose, kinds, tags, on, on_scored)


def _print_assessment(result, lang: str = "zh") -> int:
    print()
    if lang == "zh":
        print(
            f"完成 {len(result.answers)} 题，完全答对 {result.correct_count} 题，"
            f"掌握 {overall_mastery(result.scores)}%。"
        )
    else:
        print(
            f"Finished {len(result.answers)} questions, "
            f"{result.correct_count} correct, mastery {overall_mastery(result.scores)}%."
        )
    for score in sorted(result.scores, key=lambda item: (item.ability, item.topic)):
        if score.answered == 0:
            continue
        review = score.next_review or "-"
        print(
            f"  {display_topic(score.topic):22} {mastery_percent(score.ability):3d}%  "
            f"confidence {confidence_percent(score.information):3d}%  "
            f"({score.correct}/{score.answered}, credit {score.credit:.1f})  next_review {review}"
        )
    if result.autolog and result.autolog.logged:
        print(f"Logged day {result.autolog.day_index} as done (acceptance criteria met).")
    return 0


def _export_paths(raw: str) -> tuple[Path, Path]:
    path = Path(raw)
    if path.suffix.lower() == ".md":
        return path, path.with_suffix(".ics")
    if path.suffix.lower() == ".ics":
        return path.with_suffix(".md"), path
    return Path(str(path) + ".md"), Path(str(path) + ".ics")


def _write_export(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _parse_quiz(raw: str) -> tuple[int | None, int | None]:
    if not raw:
        return None, None
    if "/" not in raw:
        raise ValueError("quiz must look like 6/10")
    left, right = raw.split("/", 1)
    return int(left), int(right)


def _parse_answers(raw: str) -> list[int | str]:
    parsed: list[int | str] = []
    for piece in raw.split(","):
        token = piece.strip()
        if not token:
            continue
        if len(token) >= 2 and token.startswith("|") and token.endswith("|"):
            parsed.append(token[1:-1])
            continue
        lowered = token.lower()
        if lowered in {"a", "b", "c", "d"}:
            parsed.append(ord(lowered) - ord("a"))
        else:
            parsed.append(int(lowered))
    if not parsed:
        raise ValueError("answers were empty")
    return parsed


def _print_question(question, lang: str = "en") -> None:
    tags = f" · tags: {', '.join(question.tags)}" if question.tags else ""
    kind = "open" if question.kind == "open" else "mcq"
    label = plain_topic(question.topic, lang)
    print()
    print(
        f"[{label} · difficulty {question.difficulty} · {kind}{tags}] "
        f"{question.prompt}"
    )
    if question.kind == "open":
        print("要点：" if lang == "zh" else "Rubric:")
        for point in question.rubric:
            print(f"  - {point.label}")
        return
    for index, choice in enumerate(question.choices):
        print(f"  {chr(ord('A') + index)}. {choice}")


def _read_open(lang: str = "en") -> str:
    print("用一句话回答：" if lang == "zh" else "Answer (one line):")
    return input().strip()


def _read_choice(count: int, lang: str = "en") -> int:
    while True:
        raw = input("答案（A-D）：" if lang == "zh" else "Answer (A-D): ").strip().lower()
        if raw in "abcd"[:count]:
            return ord(raw) - ord("a")
        if raw.isdigit() and 0 <= int(raw) < count:
            return int(raw)
        print("请输入 A、B、C 或 D。" if lang == "zh" else "Enter A, B, C, or D.")


def _lang(args: argparse.Namespace, default: str) -> str:
    return normalize_lang(getattr(args, "lang", None), default)


def _print_plan(plan) -> None:
    print(
        f"7-day plan v{plan.version}  policy={plan.policy}  "
        f"{plan.daily_minutes} min/day  start={plan.start_date}"
    )
    for day in plan.days:
        print(f"Day {day.day_index}  {day.day_date}  {display_topic(day.focus)}  {day.minutes} min  [{day.status}]")
        print(f"  objective: {day.objective}")
        for criterion in day.acceptance_criteria:
            print(f"  acceptance: {criterion}")
