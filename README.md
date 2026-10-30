# Interview Study Coach

离线优先的 Python 面试学习教练。用自适应选择题摸清短板，按每天约 30 分钟生成 7 天计划（每天都有可核对的验收标准），记录完成情况，再按完成率重排下一周。默认不调用任何模型 API。

Offline-first CLI for interview prep. It estimates what you know with adaptive multiple-choice questions, builds a 7-day plan at about 30 minutes a day with measurable acceptance criteria, tracks what you finish, and replans from that completion rate. No API key is required.

## 安装 / Install

Python 3.11 or newer.

```bash
pip install -e ".[dev]"
pytest
interview-coach demo
```

The same demo is available as a module:

```bash
PYTHONPATH=src python -m interview_coach demo
```

SQLite files go under `data/` (`data/coach.sqlite` for normal use, `data/demo.sqlite` for the demo). Override the path with `--db` or `INTERVIEW_COACH_DB`.

## 命令 / Commands

```bash
interview-coach profile init --name Ada --role backend --daily-minutes 30
interview-coach assess --questions 12
interview-coach plan
interview-coach log --day 1 --minutes 30 --quiz 8/10
interview-coach log --day 2 --minutes 0 --missed
interview-coach progress
interview-coach replan
interview-coach ask "what should I study today"
```

`assess` is interactive. Pass `--answers 0,2,1` (or `A,C,B`) to run it without a terminal. `--topics python,databases` limits the check.

## 行为 / Behavior

- **Assessment.** Each topic has an ability from 1 to 5. A correct answer raises it and the next item gets harder; a miss does the opposite. Scores live in SQLite.
- **Profile.** One learner, a target role, and a daily minute budget. The default is 30 (allowed range 10–180).
- **Plan.** Seven days. Weaker topics are scheduled first. Days 1–5 are focused blocks, day 6 is mixed review, day 7 is a timed mock. Every day has numeric acceptance criteria (minutes, a score such as `6/10`, and a written deliverable).
- **Replan.** Completion is `done / (done + missed)` on days you have logged. Below 60% shrinks the next week (3 weakest topics, easier checks, 5 fewer minutes, floor 10). At least 85% complete and 70% quiz accuracy stretches it (harder checks, 5 more minutes, cap 120). Otherwise the same budget continues and unfinished topics move forward.
- **Coach.** `ask` runs an agent loop: a system prompt plus local tools (`get_profile`, `get_scores`, `get_plan`, `get_progress`, `get_today`). The default `--llm offline` fills the reply from those tool results. `--llm openai` uses the same tools through the OpenAI chat API and needs `OPENAI_API_KEY` plus `pip install -e ".[llm]"`.

## 布局 / Layout

```
src/interview_coach/
  assessment/   question bank, adaptive session, scoring
  profile/      name, role, daily minutes
  planner/      7-day plan and replan policy
  tracker/      completion rate and quiz accuracy
  agent/        prompts, local tools, offline and OpenAI clients
  cli.py        interview-coach entry point
  demo.py       scripted week
data/           SQLite databases
tests/          pytest
```

## 测试 / Tests

```bash
pip install -e ".[dev]"
pytest
```
