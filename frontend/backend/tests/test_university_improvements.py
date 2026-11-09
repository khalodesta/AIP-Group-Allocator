import pytest
from pydantic import ValidationError
from app.models import ActivityAllocation, AllocationSnapshot, Configuration, CustomUniversity, Group, Participant
from app.services.normalization import (
    display_university, normalize_university, participant_university_category,
    university_category, validate_university_classifications,
)
from app.services.scoring import score_allocation


@pytest.mark.parametrize("name,category", [
    ("Cairo University", "public"), ("ASU", "public"), ("GUC", "private"),
    ("AUC", "private"), ("Helwan National University", "national"),
    ("جامعة حلوان الأهلية", "national"), ("Galala University", "national"),
    ("Coventry Egypt", "international"), ("Unknown Fictional University", None),
])
def test_offline_categories(name, category):
    assert university_category(name) == category


@pytest.mark.parametrize("alias", ["Helwan University", "Capital University", "Capital-Helwan University", "جامعة حلوان", "جامعة العاصمة"])
def test_capital_helwan_preserves_stable_identity(alias):
    assert normalize_university(alias) == "eg-capital-university"
    assert display_university(alias) == "Capital-Helwan University"
    assert university_category(alias) == "public"
    assert normalize_university(alias) != normalize_university("Helwan National University")


def test_custom_aliases_review_and_reusable_corrections():
    people = [Participant(id=str(i), name=f"Fictional {i}", attributes={"University":"Example Academy"}) for i in range(3)]
    with pytest.raises(ValueError) as error:
        validate_university_classifications(people)
    assert str(error.value).count("Example Academy") == 1
    mappings = [CustomUniversity(id="custom:example",name="Example Academy",aliases=["EA", "Example-Academy"],category="national")]
    validate_university_classifications(people,mappings)
    assert {normalize_university(alias,mappings) for alias in ("EA", "Example Academy", "Example-Academy")} == {"custom:example"}
    assert university_category("EA",mappings) == "national"
    # Exported configuration carries the reviewed directory to another machine.
    restored=Configuration.model_validate_json(Configuration(activities=[],custom_universities=mappings).model_dump_json())
    assert university_category("EA",restored.custom_universities)=="national"
    correction=[CustomUniversity(id="eg-cairo-university",name="Cairo University",aliases=["CU"],category="other")]
    assert university_category("CU",correction)=="other"


def test_explicit_cohort_classification_and_conflicting_alias_validation():
    person=Participant(id="p",name="Fictional",attributes={"University":"Example Academy","University Category":"private"})
    assert participant_university_category(person)=="private"
    validate_university_classifications([person])
    person.attributes["University Category"]="guess"
    with pytest.raises(ValueError): validate_university_classifications([person])
    with pytest.raises(ValidationError,match="alias cannot identify two"):
        Configuration(activities=[],custom_universities=[
            CustomUniversity(id="x",name="Example X",aliases=["EA"],category="public"),
            CustomUniversity(id="y",name="Example Y",aliases=["EA"],category="private")])
    with pytest.raises(ValidationError,match="stable identity"):
        Configuration(activities=[],custom_universities=[CustomUniversity(
            id="eg-capital-university",name="Capital-Helwan University",aliases=["Helwan National University"],category="public")])
    with pytest.raises(ValueError,match="conflicting categories"):
        validate_university_classifications([
            Participant(id="p1",name="Fictional 1",attributes={"University":"Example Academy","University Category":"public"}),
            Participant(id="p2",name="Fictional 2",attributes={"University":"Example-Academy","University Category":"private"})])


def test_category_quality_includes_bus_excludes_reflection_hotel_and_gender():
    people=[Participant(id=str(i),name=f"Fictional {i}",attributes={"University":"Cairo University" if i<2 else "GUC","Gender":"Female"}) for i in range(4)]
    grouped=[Group(id="a",name="A",participant_ids=["0","1"]),Group(id="b",name="B",participant_ids=["2","3"])]
    balanced=[Group(id="a",name="A",participant_ids=["0","2"]),Group(id="b",name="B",participant_ids=["1","3"])]
    def metric(groups,activity_id="bus"):
        snapshot=AllocationSnapshot(activities=[ActivityAllocation(activity_id=activity_id,activity_name=activity_id,groups=groups)])
        return score_allocation(people,Configuration(activities=[]),snapshot)
    assert metric(balanced)["factor_balance_scores"]["university_category"] > metric(grouped)["factor_balance_scores"]["university_category"]
    for activity_id in ("reflection","hotel"):
        score=metric(grouped,activity_id)
        assert score["university_category_balance_deviation"]==0
        assert score["gender_balance_deviation"]==0
        assert score["activity_group_details"]=={}
