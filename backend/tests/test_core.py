from app.ml.models import BidFeatures
from app.ml.registry import registry
from app.nlp.text import analyze, parse_number, split_sentences, words_to_number
from app.rag.stores import catalogue_store, knowledge_store


def test_number_words():
    assert words_to_number("one hundred and twenty-five") == 125
    assert words_to_number("two dozen") == 24
    assert parse_number("1,250") == 1250
    assert parse_number("2 lakh") == 200_000


def test_analyzer_splits_units_and_compounds():
    toks = analyze("16GB RAM, ISO/IEC 27001 and Wi-Fi 6")
    assert {"16", "gb", "iso", "iec", "27001", "wi-fi", "wi", "fi"} <= set(toks)


def test_sentence_split_handles_bullets():
    assert split_sentences("Scope. We need laptops.\n- 20 monitors\n- 5 switches") == [
        "Scope.", "We need laptops.", "20 monitors", "5 switches",
    ]


def test_catalogue_retrieval_resolves_products():
    store = catalogue_store()
    assert store.search("48 port PoE switch", k=1)[0].doc.id == "MSS-NW-502"
    assert store.search("latitud 5450 notebook", k=1)[0].doc.id == "MSS-LT-101"  # typo tolerant
    assert store.search("3kva online UPS", k=1)[0].doc.id == "MSS-PW-802"


def test_knowledge_evidence_is_on_topic():
    ks = knowledge_store()
    assert ks.evidence("Bidder must hold ISO 27001 certification")[0].section == "Information security"
    assert ks.evidence("GDPR data protection obligations")[0].section == "Data protection"


def test_clause_classifier_generalises():
    clf = registry.clause_classifier()
    assert clf.metrics["holdout_accuracy"] > 0.8
    assert clf.predict_one("Proposals must be received no later than 12 November 2026.").label == "submission"
    assert clf.predict_one("All laptops must include 36 months onsite warranty.").label == "warranty_support"


def test_category_classifier():
    clf = registry.category_classifier()
    assert clf.predict_one("ceiling mounted wifi 6 APs").label == "wireless"
    assert clf.predict_one("uninterruptible power supply 1500VA").label == "power"


def test_win_model_is_monotone_in_price_and_rewards_bundles():
    model = registry.win_model()
    base = BidFeatures(price_ratio=1.0, segment="public")
    curve = model.curve(base, [0.9, 1.0, 1.1, 1.2])
    assert curve == sorted(curve, reverse=True)
    with_bundle = BidFeatures(price_ratio=1.05, bundled_value_add=True, segment="smb")
    without = BidFeatures(price_ratio=1.05, bundled_value_add=False, segment="smb")
    assert model.predict(with_bundle) > model.predict(without)
    # Public buyers are more price sensitive than enterprise buyers.
    assert model.price_elasticity("public") < model.price_elasticity("enterprise")
