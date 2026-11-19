"""Which notification kinds are e-mailed by default and which a person can switch off (Checkpoint D, CR-9)."""
from zeka.modules.comms import domain


def test_live_kinds_can_be_switched_off_and_a_support_plan_is_off_by_default():
    for kind in ("question", "answer", "plan"):
        assert kind in domain.KINDS
        assert domain.prefs_input({"email": {kind: False}}) == ({kind: False}, None)
    assert domain.wants_email({}, "answer") and not domain.wants_email({}, "plan"), "a plan follows radar: off unless chosen"
    assert domain.wants_email({"email": {"plan": True}}, "plan")
