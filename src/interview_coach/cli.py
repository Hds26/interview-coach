"""Command line for the interview study coach."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from interview_coach import __version__
from interview_coach.app import CoachApp, overall_mastery
from interview_coach.assessment.bank import TOPICS, QuestionBank, display_topic
from interview_coach.assessment.scoring import confidence_percent, mastery_percent
from interview_coach.assessment.targets import TARGETS, target_label, weight_summary
from interview_coach.db import Database
from interview_coach.demo import run_demo
from interview_coach.paths import default_db_path
from interview_coach.profile.service import DEFAULT_DAILY_MINUTES, LEVELS


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "db"):
        args.db = None
    if not hasattr(args, "llm"):
        args.llm = "offline"
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
        choices=("offline", "openai"),
        default=argparse.SUPPRESS,
        help="coach model. offline needs no API key (default)",
    )
    return shared


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_flags()
    parser = argparse.ArgumentParser(
        prog="interview-coach",
        description="Offline interview study coach: assess, plan 7 days, track, and replan.",
        parents=[shared],
    )
    parser.add_argument("--version", action="version", version=f"interview-coach {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", parents=[shared], help="run a scripted week and print the report")
    demo.set_defaults(handler=cmd_demo)

    profile = sub.add_parser("profile", parents=[shared], help="create or show the learner profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    init = profile_sub.add_parser("init", parents=[shared], help="create or replace the profile")
    init.add_argument("--name", required=True)
    init.add_argument("--role", required=True, help="job title, for example 'Backend engineer'")
    init.add_argument("--level", choices=LEVELS, default="mid")
    init.add_argument("--daily-minutes", type=int, default=DEFAULT_DAILY_MINUTES)
    init.add_argument(
        "--target",
        default="generic_tech",
        help="skill-weight preset (generic_tech, backend_engineer, python_exam, ...) or auto",
    )
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
    return parser


def cmd_demo(args: argparse.Namespace) -> int:
    path = args.db or (Path.cwd() / "data" / "demo.sqlite")
    return run_demo(path)


def cmd_profile_init(args: argparse.Namespace) -> int:
    profile = _app(args).init_profile(args.name, args.role, args.level, args.daily_minutes, args.target)
    print(
        f"Saved {profile.name} ({profile.target_role}, {profile.level}), "
        f"{profile.daily_minutes} min/day, target {profile.target_id}."
    )
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    profile = _app(args).require_profile()
    print(f"name: {profile.name}")
    print(f"role: {profile.target_role}")
    print(f"target: {profile.target_id} ({target_label(profile.target_id)})")
    print(f"weights: {weight_summary(profile.target_id)}")
    print(f"level: {profile.level}")
    print(f"daily_minutes: {profile.daily_minutes}")
    return 0


def cmd_assess(args: argparse.Namespace) -> int:
    app = _app(args)
    topics = _split_csv(args.topics)
    kinds = _split_csv(args.kinds)
    tags = _split_csv(args.tags)
    answers = _parse_answers(args.answers) if args.answers else None
    result = _run_session(app.assess, args.questions, topics, kinds, tags, answers, on=None)
    return _print_assessment(result)


def cmd_drill(args: argparse.Namespace) -> int:
    app = _app(args)
    kinds = _split_csv(args.kinds)
    tags = _split_csv(args.tags)
    answers = _parse_answers(args.answers) if args.answers else None
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
    )
    return _print_assessment(result)


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
    print(app.agent(args.llm).ask(" ".join(args.question)))
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


def _run_session(runner, count, topics, kinds, tags, answers, on):
    if answers is None and not sys.stdin.isatty():
        raise RuntimeError("pass --answers when stdin is not a terminal")

    def choose(question):
        _print_question(question)
        if answers is None:
            if question.kind == "open":
                return _read_open()
            return _read_choice(len(question.choices))
        if choose.cursor >= len(answers):
            raise RuntimeError("not enough --answers for the requested questions")
        choice = answers[choose.cursor]
        choose.cursor += 1
        if question.kind == "open":
            text = choice if isinstance(choice, str) else str(choice)
            print(f"Your answer: {text}")
            return text
        if isinstance(choice, str):
            raise ValueError("multiple-choice answers must be a letter or an index")
        if choice < 0 or choice >= len(question.choices):
            raise ValueError("answer index is out of range")
        print(f"Your answer: {chr(ord('A') + choice)}")
        return choice

    def on_scored(_question, scored) -> None:
        if scored.kind == "open":
            hits = ", ".join(scored.rubric_hits) if scored.rubric_hits else "none"
            print(f"Rubric score: {round(scored.score * 100)}% (hit: {hits})")
        else:
            print("Correct." if scored.correct else "Not correct.")

    choose.cursor = 0  # type: ignore[attr-defined]
    return runner(count, topics, choose, kinds, tags, on, on_scored)


def _print_assessment(result) -> int:
    print()
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


def _print_question(question) -> None:
    tags = f" · tags: {', '.join(question.tags)}" if question.tags else ""
    kind = "open" if question.kind == "open" else "mcq"
    print()
    print(
        f"[{display_topic(question.topic)} · difficulty {question.difficulty} · {kind}{tags}] "
        f"{question.prompt}"
    )
    if question.kind == "open":
        print("Rubric:")
        for point in question.rubric:
            print(f"  - {point.label}")
        return
    for index, choice in enumerate(question.choices):
        print(f"  {chr(ord('A') + index)}. {choice}")


def _read_open() -> str:
    print("Answer (one line):")
    return input().strip()


def _read_choice(count: int) -> int:
    while True:
        raw = input("Answer (A-D): ").strip().lower()
        if raw in "abcd"[:count]:
            return ord(raw) - ord("a")
        if raw.isdigit() and 0 <= int(raw) < count:
            return int(raw)
        print("Enter A, B, C, or D.")


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
