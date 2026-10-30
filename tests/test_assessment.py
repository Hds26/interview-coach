import pytest

from interview_coach.assessment.bank import QUESTIONS, TOPICS, QuestionBank
from interview_coach.assessment.engine import AdaptiveAssessment


def test_bank_covers_every_topic_and_difficulty():
    ids = [question.id for question in QUESTIONS]
    assert len(ids) == len(set(ids))
    bank = QuestionBank()
    for topic in TOPICS:
        items = bank.for_topic(topic)
        assert {question.difficulty for question in items} == {1, 2, 3, 4, 5}
        for question in items:
            assert 0 <= question.answer < len(question.choices)


def test_correct_answers_move_toward_harder_items():
    bank = QuestionBank()
    engine = AdaptiveAssessment(bank, topics=["complexity"], prior={"complexity": 1.0})
    seen = []
    for _ in range(4):
        question = engine.next_question()
        assert question is not None
        seen.append(question.difficulty)
        engine.submit(question.id, question.answer)
    assert seen[0] < seen[-1]
    assert engine.ability["complexity"] > 1.0


def test_wrong_answers_move_toward_easier_items():
    bank = QuestionBank()
    engine = AdaptiveAssessment(bank, topics=["databases"], prior={"databases": 5.0})
    seen = []
    for _ in range(4):
        question = engine.next_question()
        assert question is not None
        seen.append(question.difficulty)
        wrong = (question.answer + 1) % len(question.choices)
        engine.submit(question.id, wrong)
    assert seen[0] > seen[-1]
    assert engine.ability["databases"] < 5.0


def test_questions_are_not_repeated():
    bank = QuestionBank()
    engine = AdaptiveAssessment(bank, topics=["python"])
    asked = []
    for _ in range(5):
        question = engine.next_question()
        assert question is not None
        asked.append(question.id)
        engine.submit(question.id, 0)
    assert len(asked) == len(set(asked))
    assert engine.next_question() is None


def test_unknown_topic_is_rejected():
    with pytest.raises(ValueError):
        AdaptiveAssessment(QuestionBank(), topics=["not-a-topic"])
