"""Regression cases for discovery coverage lost through over-aggressive dedup."""

from itertools import permutations

import pytest

from models import HackathonEvent
from storage.json_store import EventStore
from utils.event_identity import (
    alternate_url_list, prune_unrelated_alternate_urls,
    deduplicate_event_dicts, deduplicate_events, editions_compatible,
    merge_event_evidence, same_event,
)


def event(title="PoliHack Milano 2026", url="https://example.org/event", **kwargs):
    return HackathonEvent(title=title, url=url, source=kwargs.pop("source", "test"), **kwargs)


@pytest.mark.parametrize("left,right", [
    (event("PoliHack 2026"), event("PoliHack 2027", url="https://other.org/event")),
    (event(date_str="2026-10-20"), event(url="https://other.org/event", date_str="2026-11-20")),
    (event("PoliHack 2nd edition"), event("PoliHack 3rd edition", url="https://other.org/event")),
    (event("PoliHack 2.0"), event("PoliHack 3.0", url="https://other.org/event")),
    (event("PoliHack", url="https://example.org/2026"), event("PoliHack", url="https://other.org/2027")),
])
def test_explicit_incompatible_editions_are_not_duplicates(left, right):
    assert not same_event(left, right)
    assert not same_event(right, left)
    assert len(deduplicate_events([left, right])) == 2


@pytest.mark.parametrize("left_title,right_title", [
    ("Hackathon AI Milano", "Hackathon AI Milano 2026"),
    ("Microsoft Healthcare Hackathon", "Microsoft Finance Hackathon"),
    ("Green Innovation Sprint", "Blue Innovation Sprint"),
    ("Microsoft Sustainability Hackathon", "Microsoft Social Good Hackathon"),
    ("Machine Learning Hackathon", "Machine Learning Hackathon Milano"),
    ("Delta Artificial Intelligence Society Hackathon", "Sigma Artificial Intelligence Society Hackathon"),
    ("Hackathon del Club Universitario Alpha", "Hackathon del Club Universitario Beta"),
    ("Hackathon Ferrara Lab Alpha Milano", "Hackathon Ferrara Lab Beta Milano"),
])
def test_generic_topic_or_organizer_does_not_identify_an_event(left_title, right_title):
    left = event(left_title, date_str="2026-10-20", description="Build software with our developer community.")
    right = event(right_title, url="https://other.org/event", date_str="2026-10-20",
                  description="Build software with our developer community.")
    assert not same_event(left, right)


def test_real_fuzzy_title_variant_still_matches():
    left = event("PoliHack Milano 2026 Hackathon")
    right = event("PoliHack Milano 2026 Hackathon Edition", url="https://other.org/ph")
    assert same_event(left, right)


def test_official_and_editorial_wikimedia_records_match():
    left = event("Il Wikimedia Hackathon 2026 arriva a Milano - Wikimedia Italia",
                 url="https://wikimedia.it/news/event", date_str="2026-05-01", source="web_search")
    right = event("[Wikitech-l] Reminder: Registration for the 2026 Wikimedia ...",
                  url="https://lists.wikimedia.org/hyperkitty/thread/event", date_str="2026-05-01",
                  source="web_search", description="The Wikimedia Hackathon takes place in Milan on May 1-3.")
    merged = deduplicate_events([right, left])
    assert len(merged) == 1
    assert merged[0].url == left.url
    assert right.url in merged[0].alternate_urls


def test_cross_reference_words_in_different_order_are_not_identity():
    left = event("Amber River Lighthouse", date_str="2026-11-02")
    right = event("Amber Community Workshop", url="https://other.org/event", date_str="2026-11-02",
                  description="The lighthouse is near a river with amber on the bank.")
    assert not same_event(left, right)


def test_luma_aliases_match_without_changing_primary_url_id():
    left = event(url="https://lu.ma/abc?utm_source=search")
    right = event(url="https://luma.com/abc", source="web_search")
    assert left.id != right.id
    assert same_event(left, right)
    merged = deduplicate_events([right, left])
    assert len(merged) == 1
    assert merged[0].id == left.id
    assert right.url in merged[0].alternate_urls


def test_same_url_collectors_merge_complementary_evidence_independent_of_completion_order():
    snippet = event(source="web_search", description="Search snippet", organizer="PoliMi")
    detail = event(date_str="2026-10-20", location="Milano", description="Verified details from the event card")
    third = event(url="https://example.org/event?utm_source=mail", source="web_search",
                  alternate_urls=["https://other.org/official"])
    expected = None
    for order in permutations([snippet, detail, third]):
        records = [record.to_dict() for record in order]
        result = deduplicate_event_dicts(records)
        expected = expected or result
        assert result == expected
        assert len(result) == 1
        assert result[0]["date_str"] == "2026-10-20"
        assert result[0]["location"] == "Milano"
        assert result[0]["organizer"] == "PoliMi"
        assert result[0]["description"] == detail.description
        assert result[0]["alternate_urls"] == ["https://other.org/official"]
    assert snippet.location == ""
    assert detail.organizer == ""


def test_same_url_conflicting_editions_keep_latest_coherent_record_without_invented_fields():
    old = event("PoliHack 2025", date_str="2025-10-20", location="Old venue", organizer="Old organizer")
    new = event("PoliHack 2026", date_str="2026-10-20", description="New edition")
    result = deduplicate_events([old, new])
    assert result[0].id == new.id == old.id
    assert result[0].title == new.title
    assert result[0].description == new.description
    assert result[0].location == ""
    assert result[0].organizer == ""
    assert result[0].to_dict() == deduplicate_events([new, old])[0].to_dict()


def test_different_url_conflicting_editions_cannot_be_merged():
    with pytest.raises(ValueError, match="incompatible"):
        merge_event_evidence(event("PoliHack 2026"), event("PoliHack 2027", url="https://other.org/event"))


@pytest.mark.parametrize("provenance", ["publication", "unknown", "deadline"])
def test_publication_or_unknown_dates_do_not_block_same_event(provenance):
    left = event(date_str="2026-10-20").to_dict()
    right = event(date_str="2026-09-01").to_dict()
    right["date_source"] = provenance
    assert editions_compatible(left, right)
    assert same_event(left, right)


def test_store_preserves_separate_editions_and_does_not_add_false_alternate(tmp_path):
    store = EventStore(path=tmp_path / "events.json")
    old = event(date_str="2026-10-20")
    new = event(url="https://other.org/event", date_str="2026-11-20")
    store.add_event(old)
    assert not store.is_duplicate(new)
    assert store.all_events()[0]["alternate_urls"] == []
    store.add_event(new)
    assert store.count == 2


def test_store_sends_changed_edition_on_same_url_back_to_classification(tmp_path):
    store = EventStore(path=tmp_path / "events.json")
    old, new = event("PoliHack 2025"), event("PoliHack 2026")
    store.add_event(old)
    assert not store.is_duplicate(new)
    store.add_event(new)
    assert store.count == 1
    assert store.all_events()[0]["title"] == new.title


def test_store_keeps_normalized_alternate_urls(tmp_path):
    store = EventStore(path=tmp_path / "events.json")
    original = event()
    duplicate = event(url="https://other.org/event?utm_source=search",
                      alternate_urls=["https://third.org/event/"])
    store.add_event(original)
    assert store.is_duplicate(duplicate)
    assert store.all_events()[0]["alternate_urls"] == ["https://other.org/event", "https://third.org/event"]
    assert store.is_duplicate(event("Unrelated shortened title", url="https://third.org/event"))


MEETUP = "https://www.meetup.com/master-the-vibe-milan/events"


def test_meetup_listing_parameters_do_not_create_a_new_identity():
    listed = event("Hackathon di Natale!", url=f"{MEETUP}/315691626/?recId=17b7&recSource=event-search")
    group = event("Hackathon di Natale!", url=f"{MEETUP}/315691626/?eventOrigin=group_upcoming_events")
    assert same_event(listed, group)
    assert len(deduplicate_events([listed, group])) == 1


def test_a_stale_alias_cannot_merge_two_meetup_events(tmp_path):
    # 2026-10-24: another event of the same group was discarded as "already known"
    # because its URL had been saved as an alias of "Hackathon di Natale!".
    store = EventStore(path=tmp_path / "events.json")
    store.add_event(event("Hackathon di Natale!", url=f"{MEETUP}/315691626/",
                          alternate_urls=[f"{MEETUP}/315691522?eventOrigin=group_upcoming_events"]))
    other = event("LLM FinOps", url=f"{MEETUP}/315691522/?eventOrigin=group_upcoming_events")
    assert not store.is_duplicate(other)


def test_alias_list_keeps_one_url_per_meetup_event_and_never_another_event():
    aliases = alternate_url_list(f"{MEETUP}/315691626/", [
        f"{MEETUP}/315691626/?recId=a",          # the primary event itself
        f"{MEETUP}/315691522/",                  # another event of the group
        "https://luma.com/abc",
    ])
    assert aliases == ["https://luma.com/abc"]
    aliases = alternate_url_list("https://example.org/event", [
        "https://www.meetup.com/g/events/1/?recId=a", "https://www.meetup.com/g/events/1/?recId=b",
    ])
    assert len(aliases) == 1


def test_legacy_alias_repair_keeps_pages_that_name_the_event_only():
    record = event("Hackathon per universitari Talenti STEM per l'Innovazione Sociale",
                   url="https://fondazionetriulza.org/hackathon-talenti-stem-deadline-19-ottobre").to_dict()
    record["alternate_urls"] = [
        "https://www.unimib.it/news/hackathon-talenti-stem-linnovazione-sociale",
        "https://fondazionetriulza.org",                                 # organizer homepage
        "https://myaccount.microsoft.com/login",                         # login page
        "https://www.meetup.com/ac-phx/events/316530156?recId=73dc620c",  # foreign Meetup event
    ]
    repaired, dropped = prune_unrelated_alternate_urls(record)
    assert repaired["alternate_urls"] == ["https://www.unimib.it/news/hackathon-talenti-stem-linnovazione-sociale"]
    assert len(dropped) == 3
    assert record["alternate_urls"][1] == "https://fondazionetriulza.org"  # input untouched


@pytest.mark.parametrize("variant", [
    "https://meetup.com/it-IT/master-the-vibe-milan/events/315691626/?recId=x",
    "https://www.meetup.com/en-US/master-the-vibe-milan/events/315691626",
    "http://www.meetup.com/renamed-group/events/315691626/?eventOrigin=find_page",
])
def test_meetup_event_number_is_the_identity_under_any_url_variant(tmp_path, variant):
    # A later discovery may carry a locale path and a translated title.
    original = event("Hackathon di Natale!", url=f"{MEETUP}/315691626/")
    translated = event("Christmas Hackathon!", url=variant, source="web_search")
    assert same_event(original, translated)
    store = EventStore(path=tmp_path / "events.json")
    store.add_event(original)
    assert store.is_duplicate(translated)
    assert store.all_events()[0]["alternate_urls"] == []  # no alias needed for the same number
