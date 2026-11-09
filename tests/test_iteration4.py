"""Iteration 4: Chinese items, evidenced weaknesses, kinds, streak, and plan honesty."""

import re
from datetime import date, timedelta

from interview_coach.app import CoachApp
from interview_coach.assessment.bank import TOPICS, QuestionBank
from interview_coach.assessment.open_items import open_question_for
from interview_coach.assessment.rubric import score_rubric
from interview_coach.assessment.targets import infer_target
from interview_coach.cli import main
from interview_coach.db import Database
from interview_coach.models import TopicScore
from interview_coach.planner.planner import build_week

CJK = re.compile(r"[\u4e00-\u9fff]")


def _perfect(question):
    if question.kind == "open":
        return " ".join(point.keywords[0] for point in question.rubric if point.keywords)
    return question.answer


def _wrong(question):
    if question.kind == "open":
        return "不会"
    return (question.answer + 1) % len(question.choices)


def _bar(days) -> float:
    for criterion in days[0].acceptance_criteria:
        if "Open item" in criterion:
            continue
        match = re.search(r"at least (\d+)/(\d+)", criterion)
        if match:
            return int(match.group(1)) / int(match.group(2))
    raise AssertionError(days[0].acceptance_criteria)


def test_items_are_chinese_and_each_topic_has_more_than_one_open_item():
    bank = QuestionBank()
    for topic in TOPICS:
        items = bank.for_topic(topic)
        multiple_choice = [question for question in items if question.kind == "mcq"]
        opened = [question for question in items if question.kind == "open"]
        assert len(multiple_choice) > 6
        assert len(opened) >= 2
        assert len({question.id for question in opened}) == len(opened)
    for question in bank.questions:
        assert CJK.search(question.prompt)
        assert CJK.search(question.explanation)
        if question.kind == "open":
            assert any(CJK.search(point.label) for point in question.rubric)


def test_chinese_answer_scores_and_negation_does_not():
    python = open_question_for("python")
    full = score_rubric(python, "默认参数在定义时只创建一次，之后被共享，这个列表是可变的")
    assert full.hit_points == 3
    complexity = open_question_for("complexity")
    assert score_rubric(complexity, "这些数是无序的").hit_points == 0
    assert score_rubric(complexity, "数组有序，每次丢掉一半，所以是对数").hit_points == 3


def test_today_assess_and_drill_show_chinese_items(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "后端"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                *db,
                "today",
                "--on",
                "2026-04-01",
                "--questions",
                "1",
                "--kinds",
                "mcq",
                "--answers",
                "1",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "脏读" in output
    assert "没对" in output
    assert "说明" in output
    assert "A dirty read" not in output
    assert "Not correct" not in output

    assert (
        main(
            [
                *db,
                "--lang",
                "en",
                "assess",
                "--topics",
                "databases",
                "--kinds",
                "mcq",
                "--questions",
                "1",
                "--answers",
                "1",
            ]
        )
        == 0
    )
    english = capsys.readouterr().out
    assert "Not correct." in english
    assert "Explanation:" in english
    assert CJK.search(english)

    app = CoachApp(Database(tmp_path / "drill.sqlite"))
    app.init_profile("Ada", "后端")
    app.db.conn.execute(
        """
        UPDATE topic_score
        SET ability = 2.0, answered = 1, correct = 0, next_review = '2026-04-01'
        WHERE topic = 'databases'
        """
    )
    app.db.conn.commit()
    code = main(
        [
            "--db",
            str(tmp_path / "drill.sqlite"),
            "drill",
            "--on",
            "2026-04-01",
            "--questions",
            "1",
            "--kinds",
            "mcq",
            "--answers",
            "1",
        ]
    )
    assert code == 0
    drilled = capsys.readouterr().out
    assert CJK.search(drilled)
    assert "没对" in drilled
    assert "说明" in drilled
    assert "Equality and range" not in drilled


def test_weak_line_needs_evidence_and_prints_on_a_failed_day(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "generalist", target="generic_tech")
    setup = app.prepare_today(on=date(2026, 4, 1))
    assert setup.day.focus == "arrays_hashing"
    failed = app.assess(
        4,
        setup.topics,
        _wrong,
        kinds=["mcq"],
        on=date(2026, 4, 1),
        must_ask=(),
    )
    assert failed.autolog is not None and failed.autolog.logged is False
    closing = app.closing_lines(failed, "zh", on=date(2026, 4, 1))
    weak = [line for line in closing if "较薄弱" in line]
    assert weak
    assert "数组" in weak[0]
    assert "复杂度" not in weak[0]
    assert "并发" not in weak[0]
    assert "数据库" not in weak[0]

    perfect = CoachApp(Database(tmp_path / "perfect.sqlite"))
    perfect.init_profile("Ada", "generalist", target="generic_tech")
    ready = perfect.prepare_today(on=date(2026, 4, 1))
    done = perfect.assess(
        5,
        ready.topics,
        _perfect,
        kinds=ready.kinds,
        must_ask=ready.must_ask,
        on=date(2026, 4, 1),
    )
    assert done.autolog is not None and done.autolog.logged is True
    logged = perfect.closing_lines(done, "zh", on=date(2026, 4, 1))
    assert not any("较薄弱" in line for line in logged)


def test_kinds_change_the_today_mix_and_drop_impossible_checks(tmp_path):
    app = CoachApp(Database(tmp_path / "mcq.sqlite"))
    app.init_profile("Ada", "generalist", target="generic_tech", preferred_kinds="mcq")
    setup = app.prepare_today(on=date(2026, 4, 1))
    assert setup.kinds == ["mcq"]
    assert setup.must_ask == ()
    assert all("Open item" not in line and "开放题" not in line for line in setup.lines)
    assert all("Write 3" not in line and "定义" not in line for line in setup.lines)
    result = app.assess(
        5,
        setup.topics,
        _perfect,
        kinds=setup.kinds,
        must_ask=setup.must_ask,
        on=date(2026, 4, 1),
    )
    assert result.answers
    assert all(answer.kind == "mcq" for answer in result.answers)
    assert result.autolog is not None and result.autolog.logged is True

    opened = CoachApp(Database(tmp_path / "open.sqlite"))
    opened.init_profile("Ada", "generalist", target="generic_tech", preferred_kinds="open")
    open_setup = opened.prepare_today(on=date(2026, 4, 1))
    assert open_setup.kinds == ["open"]
    assert open_setup.must_ask
    assert any("开放题" in line for line in open_setup.lines)
    assert all("练习至少对" not in line for line in open_setup.lines)
    open_result = opened.assess(
        2,
        open_setup.topics,
        _perfect,
        kinds=["open"],
        must_ask=open_setup.must_ask,
        on=date(2026, 4, 1),
    )
    assert all(answer.kind == "open" for answer in open_result.answers)
    assert open_result.autolog is not None and open_result.autolog.logged is True


def test_cli_kinds_flag_changes_today(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "后端"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                *db,
                "today",
                "--on",
                "2026-04-01",
                "--kinds",
                "mcq",
                "--questions",
                "2",
                "--answers",
                "0,1",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "· mcq" in output
    assert "· open" not in output


def test_streak_breaks_when_a_day_is_skipped(tmp_path, capsys):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "generalist", target="generic_tech", preferred_kinds="mcq")
    first = app.prepare_today(on=date(2026, 4, 1))
    done = app.assess(
        5,
        first.topics,
        _perfect,
        kinds=["mcq"],
        must_ask=(),
        on=date(2026, 4, 1),
    )
    assert done.autolog is not None and done.autolog.logged is True
    assert app.current_streak(date(2026, 4, 1)) == 1

    later = app.prepare_today(on=date(2026, 4, 3))
    plan = app.db.get_active_plan()
    assert any(day.status == "missed" for day in plan.days)
    assert any("记为错过" in line for line in later.lines)
    assert app.current_streak(date(2026, 4, 3)) == 0
    finished = app.assess(
        5,
        later.topics,
        _perfect,
        kinds=later.kinds,
        must_ask=later.must_ask,
        on=date(2026, 4, 3),
    )
    assert finished.autolog is not None and finished.autolog.logged is True
    assert app.current_streak(date(2026, 4, 3)) == 1
    closing = "\n".join(app.closing_lines(finished, "zh", on=date(2026, 4, 3)))
    assert "连续打卡 1" in closing
    assert "连续目标" not in closing
    assert "错过" in closing

    start = (date.today() - timedelta(days=14)).isoformat()
    db = ["--db", str(tmp_path / "progress.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "后端"]) == 0
    assert main([*db, "plan", "--start", start]) == 0
    capsys.readouterr()
    assert main([*db, "progress"]) == 0
    progress = capsys.readouterr().out
    assert "streak: 0" in progress
    assert "overdue:" in progress
    assert "minutes_spent: 0" in progress


def test_job_title_infers_backend_and_omitted_init_flags_stay(tmp_path, capsys):
    assert infer_target("后端") == "backend_engineer"
    assert infer_target("Backend engineer") == "backend_engineer"
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "Backend engineer"]) == 0
    assert main([*db, "profile", "show"]) == 0
    shown = capsys.readouterr().out
    assert "target: backend_engineer" in shown
    assert main([*db, "plan", "--start", "2026-04-01"]) == 0
    planned = capsys.readouterr().out
    assert "Day 1" in planned
    assert "Databases" in planned.split("Day 2")[0]

    assert (
        main(
            [
                *db,
                "profile",
                "init",
                "--name",
                "Ada",
                "--role",
                "Backend engineer",
                "--level",
                "senior",
                "--daily-minutes",
                "40",
                "--target",
                "backend_engineer",
                "--streak-goal",
                "9",
                "--kinds",
                "open",
            ]
        )
        == 0
    )
    assert main([*db, "profile", "init", "--name", "Bea", "--role", "frontend engineer"]) == 0
    assert main([*db, "profile", "show"]) == 0
    kept = capsys.readouterr().out
    assert "name: Bea" in kept
    assert "role: frontend engineer" in kept
    assert "level: senior" in kept
    assert "daily_minutes: 40" in kept
    assert "target: backend_engineer" in kept
    assert "streak_goal: 9" in kept
    assert "preferred_kinds: open" in kept

    explicit = ["--db", str(tmp_path / "generic.sqlite")]
    assert (
        main(
            [
                *explicit,
                "profile",
                "init",
                "--name",
                "Ada",
                "--role",
                "Backend engineer",
                "--target",
                "generic_tech",
            ]
        )
        == 0
    )
    assert main([*explicit, "plan", "--start", "2026-04-01"]) == 0
    generic = capsys.readouterr().out
    assert "Arrays & Hashing" in generic.split("Day 2")[0]


def test_shrink_week_does_not_raise_the_score_bar():
    mid = [TopicScore(topic, 3.0, 0, 0) for topic in TOPICS]
    high = [TopicScore(topic, 4.2, 0, 0) for topic in TOPICS]
    assert _bar(build_week(mid, 25, policy="shrink")) <= _bar(build_week(mid, 30, policy="steady"))
    assert _bar(build_week(mid, 25, policy="shrink")) < 7 / 10
    assert _bar(build_week(high, 25, policy="shrink")) <= _bar(build_week(high, 30, policy="steady"))
    blob = " ".join(
        criterion
        for day in build_week(mid, 30)
        for criterion in day.acceptance_criteria
    )
    assert "Write 3" not in blob
    assert "definitions" not in blob


def test_ask_routes_weakness_to_evidence(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "generalist", target="generic_tech")
    app.create_plan(start=date(2026, 4, 1))
    empty = app.agent("offline").ask("我哪里弱")
    assert "不能判断" in empty
    assert "复杂度" not in empty
    assert "并发" not in empty
    assert "数据库" not in empty
    app.assess(1, ["arrays_hashing"], _wrong, kinds=["mcq"])
    answered = app.agent("offline").ask("我哪里弱")
    assert "目前较薄弱" in answered
    assert "数组" in answered
    assert "并发" not in answered
    assert "数据库" not in answered


def test_auto_log_minutes_are_elapsed_and_plan_follows_weak_topics(tmp_path, capsys):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "generalist", target="generic_tech", preferred_kinds="mcq")
    setup = app.prepare_today(on=date(2026, 4, 1))
    done = app.assess(5, setup.topics, _perfect, kinds=["mcq"], must_ask=(), on=date(2026, 4, 1))
    assert done.autolog is not None and done.autolog.logged is True
    logged = app.db.list_logs(app.db.get_active_plan().id)
    assert logged[-1].minutes_spent < 5
    assert app.progress().minutes_spent < 5

    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "progress"]) == 0
    assert "minutes_spent: 30" not in capsys.readouterr().out

    same_ability = []
    for topic in TOPICS:
        if topic == "networking":
            same_ability.append(TopicScore(topic, 3.0, 3, 0, 0.0, 0.0))
        else:
            same_ability.append(TopicScore(topic, 3.0, 0, 0))
    assert build_week(same_ability, 30)[0].focus == "networking"

    adapted = CoachApp(Database(tmp_path / "adapt.sqlite"))
    adapted.init_profile("Ada", "generalist", target="generic_tech")
    plan = adapted.create_plan(start=date(2026, 4, 1))
    assert plan.days[0].focus == "arrays_hashing"
    assert plan.days[1].focus == "complexity"
    adapted.log_day(1, 5, True, 5, 5)
    adapted.db.conn.execute(
        "UPDATE topic_score SET ability = 3.0, answered = 4, correct = 1, credit = 1 WHERE topic = 'databases'"
    )
    adapted.db.conn.commit()
    adapted.assess(1, ["databases"], _wrong, kinds=["mcq"], on=date(2026, 4, 1))
    pending = [day for day in adapted.db.get_active_plan().days if day.status == "pending"]
    assert pending[0].focus == "databases"


def test_repeated_topic_uses_a_different_open_item():
    scores = [
        TopicScore("databases", 1.5, 4, 1),
        TopicScore("networking", 2.0, 4, 2),
        TopicScore("system_design", 2.4, 4, 2),
        TopicScore("arrays_hashing", 3.0, 4, 2),
        TopicScore("concurrency", 3.2, 4, 2),
        TopicScore("complexity", 3.4, 4, 3),
        TopicScore("trees_graphs", 4.0, 4, 3),
        TopicScore("python", 4.5, 4, 4),
    ]
    days = build_week(scores, 25, policy="shrink")
    first = days[0].acceptance_criteria[-1]
    second = days[3].acceptance_criteria[-1]
    assert days[0].focus == "databases"
    assert days[3].focus == "databases"
    assert "Open item db-open:" in first
    assert "Open item db-open-2:" in second
