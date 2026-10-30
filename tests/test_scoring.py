from interview_coach.assessment.scoring import (
    MAX_ABILITY,
    MIN_ABILITY,
    expected_correct,
    item_information,
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


def test_discrimination_scales_the_step_and_the_information():
    gentle = update_ability(3.0, 3.0, True, discrimination=0.8)
    sharp = update_ability(3.0, 3.0, True, discrimination=1.3)
    assert sharp > gentle > 3.0
    assert item_information(3, 3, 1.3) > item_information(3, 3, 0.8)
    assert item_information(3, 3, 1) > item_information(3, 5, 1)


def test_partial_credit_moves_ability_toward_the_score():
    assert update_ability(3.0, 3.0, 0.5) == 3.0
    assert update_ability(3.0, 3.0, 1.0) > 3.0
    assert update_ability(3.0, 3.0, 0.0) < 3.0


def test_confidence_grows_with_informative_answers():
    from interview_coach.assessment.scoring import confidence_percent

    information = 0.0
    previous = -1
    for _ in range(6):
        information += item_information(3, 3, 1)
        confidence = confidence_percent(information)
        assert previous < confidence < 100
        previous = confidence
    assert confidence_percent(0) == 0
