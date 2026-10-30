"""Command line for the interview study coach."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from interview_coach import __version__
from interview_coach.app import CoachApp, overall_mastery
from interview_coach.assessment.bank import TOPICS, display_topic
from interview_coach.assessment.scoring import mastery_percent
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
    init.add_argument("--role", required=True)
    init.add_argument("--level", choices=LEVELS, default="mid")
    init.add_argument("--daily-minutes", type=int, default=DEFAULT_DAILY_MINUTES)
    init.set_defaults(handler=cmd_profile_init)
    show = profile_sub.add_parser("show", parents=[shared], help="print the profile")
    show.set_defaults(handler=cmd_profile_show)

    assess = sub.add_parser("assess", parents=[shared], help="run an adaptive multiple-choice check")
    assess.add_argument("--questions", type=int, default=12)
    assess.add_argument("--topics", default="", help="comma-separated topic ids")
    assess.add_argument("--answers", default="", help="comma-separated letters or 0-based indexes")
    assess.set_defaults(handler=cmd_assess)

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

    topics = sub.add_parser("topics", parents=[shared], help="list topic ids")
    topics.set_defaults(handler=cmd_topics)
    return parser


def cmd_demo(args: argparse.Namespace) -> int:
    path = args.db or (Path.cwd() / "data" / "demo.sqlite")
    return run_demo(path)


def cmd_profile_init(args: argparse.Namespace) -> int:
    profile = _app(args).init_profile(args.name, args.role, args.level, args.daily_minutes)
    print(
        f"Saved {profile.name} ({profile.target_role}, {profile.level}), "
        f"{profile.daily_minutes} min/day."
    )
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    profile = _app(args).require_profile()
    print(f"name: {profile.name}")
    print(f"role: {profile.target_role}")
    print(f"level: {profile.level}")
    print(f"daily_minutes: {profile.daily_minutes}")
    return 0


def cmd_assess(args: argparse.Namespace) -> int:
    app = _app(args)
    topics = [item.strip() for item in args.topics.split(",") if item.strip()] or None
    answers = _parse_answers(args.answers) if args.answers else None
    if answers is None and not sys.stdin.isatty():
        raise RuntimeError("pass --answers when stdin is not a terminal")

    def choose(question):
        _print_question(question)
        if answers is None:
            return _read_choice(len(question.choices))
        if choose.cursor >= len(answers):
            raise RuntimeError("not enough --answers for the requested questions")
        choice = answers[choose.cursor]
        choose.cursor += 1
        if choice < 0 or choice >= len(question.choices):
            raise ValueError("answer index is out of range")
        print(f"Your answer: {chr(ord('A') + choice)}")
        return choice

    choose.cursor = 0  # type: ignore[attr-defined]
    result = app.assess(args.questions, topics, choose)
    print()
    print(
        f"Finished {len(result.answers)} questions, "
        f"{result.correct_count} correct, mastery {overall_mastery(result.scores)}%."
    )
    for score in sorted(result.scores, key=lambda item: (item.ability, item.topic)):
        if score.answered == 0:
            continue
        print(
            f"  {display_topic(score.topic):22} {mastery_percent(score.ability):3d}%  "
            f"({score.correct}/{score.answered})"
        )
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    plan = _app(args).create_plan(start=_parse_date(args.start), force=args.force)
    _print_plan(plan)
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    progress = _app(args).progress()
    print(f"plan: v{progress.version}")
    print(f"done: {progress.days_done}  missed: {progress.days_missed}  pending: {progress.days_pending}")
    print(f"reported_completion: {round(progress.reported_completion * 100)}%")
    print(f"quiz_accuracy: {round(progress.quiz_accuracy * 100)}%")
    print(f"minutes_spent: {progress.minutes_spent}")
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
    for topic, label in TOPICS.items():
        print(f"{topic:16} {label}")
    return 0


def _app(args: argparse.Namespace) -> CoachApp:
    return CoachApp(Database(args.db or default_db_path()))


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("start date must be YYYY-MM-DD") from exc


def _parse_quiz(raw: str) -> tuple[int | None, int | None]:
    if not raw:
        return None, None
    if "/" not in raw:
        raise ValueError("quiz must look like 6/10")
    left, right = raw.split("/", 1)
    return int(left), int(right)


def _parse_answers(raw: str) -> list[int]:
    parsed: list[int] = []
    for piece in raw.split(","):
        token = piece.strip().lower()
        if not token:
            continue
        if token in {"a", "b", "c", "d"}:
            parsed.append(ord(token) - ord("a"))
        else:
            parsed.append(int(token))
    if not parsed:
        raise ValueError("answers were empty")
    return parsed


def _print_question(question) -> None:
    print()
    print(f"[{display_topic(question.topic)} · difficulty {question.difficulty}] {question.prompt}")
    for index, choice in enumerate(question.choices):
        print(f"  {chr(ord('A') + index)}. {choice}")


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
