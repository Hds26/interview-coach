from interview_coach.assessment.scoring import (
    MAX_ABILITY,
    MIN_ABILITY,
    expected_correct,
    mastery_percent,
    update_ability,
)


def test_correct_answer_raises_ability_and_wrong_answer_lowers_it():
    up = update_ability(3.0, 3.0, True)
    down = update_ability(3.0, 3.0, False)
    assert up > 3.0 > down


def test_ability_stays_inside_the_scale():
    ability = MAX_ABILITY
    for _ in range(12):
        ability = update_ability(ability, 1, True)
    assert ability == MAX_ABILITY
    ability = MIN_ABILITY
    for _ in range(12):
        ability = update_ability(ability, 5, False)
    assert ability == MIN_ABILITY


def test_expected_correct_is_a_probability():
    assert expected_correct(3, 3) == 0.5
    assert 0 < expected_correct(1, 5) < expected_correct(5, 1) < 1


def test_mastery_maps_the_scale_onto_percent():
    assert mastery_percent(1) == 0
    assert mastery_percent(3) == 50
    assert mastery_percent(5) == 100
