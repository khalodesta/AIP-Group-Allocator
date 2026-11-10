import pytest
from pydantic import ValidationError
from app.models import ActivityAllocation, AllocationSnapshot, Configuration, CustomUniversity, Group, Participant
from app.services.normalization import (
    display_university, normalize_university, participant_university_category,
    university_category, university_directory, validate_university_classifications,
)
from app.services.scoring import score_allocation


@pytest.mark.parametrize("name,category", [
    ("Cairo University", "public"), ("ASU", "public"), ("GUC", "private"),
    ("AUC", "private"), ("Helwan National University", None),
    ("جامعة حلوان الأهلية", None), ("Galala University", None),
    ("Coventry Egypt", None), ("Unknown Fictional University", None),
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
    mappings = [CustomUniversity(id="custom:example",name="Example Academy",aliases=["EA", "Example-Academy"],category="private")]
    validate_university_classifications(people,mappings)
    assert {normalize_university(alias,mappings) for alias in ("EA", "Example Academy", "Example-Academy")} == {"custom:example"}
    assert university_category("EA",mappings) == "private"
    # Exported configuration carries the reviewed directory to another machine.
    restored=Configuration.model_validate_json(Configuration(activities=[],custom_universities=mappings).model_dump_json())
    assert university_category("EA",restored.custom_universities)=="private"
    correction=[CustomUniversity(id="eg-cairo-university",name="Cairo University",aliases=["CU"],category="private")]
    assert university_category("CU",correction)=="private"


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


@pytest.mark.parametrize("category",["national","international","other","unclassified",""])
def test_only_public_and_private_can_be_confirmed(category):
    with pytest.raises(ValidationError):
        CustomUniversity(id="example",name="Fictional Academy",aliases=[],category=category)
    person=Participant(id="p",name="Fictional",attributes={"University":"Fictional Academy","University Category":category})
    assert participant_university_category(person) is None
    with pytest.raises(ValueError,match="Confirm Public or Private"):
        validate_university_classifications([person])


def test_legal_metadata_never_guesses_a_binary_grouping_category():
    assert {entry.get("diversity_category") for entry in university_directory()} <= {"public","private",None}
    for name in ("Helwan National University","Coventry Egypt","Galala University"):
        person=Participant(id="p",name="Fictional",attributes={"University":name})
        with pytest.raises(ValueError,match="University classification required"):
            validate_university_classifications([person])
    mapping=CustomUniversity(id="eg-helwan-national-university",name="Helwan National University",aliases=["HNU"],category="private")
    assert university_category("HNU",[mapping])=="private"
    assert next(u for u in university_directory() if u["id"]==mapping.id)["category"]=="national_ahlia"


def test_one_explicit_cohort_confirmation_applies_to_all_same_university_rows():
    people=[Participant(id="p1",name="Fictional One",attributes={"University":"Fictional Academy","University Category":"private"}),
            Participant(id="p2",name="Fictional Two",attributes={"University":"fictional-academy"})]
    validate_university_classifications(people)
    assert [person.attributes["University Category"] for person in people]==["private","private"]


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
