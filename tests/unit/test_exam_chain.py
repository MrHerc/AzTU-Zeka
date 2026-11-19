"""The exam's hash chain (tasks/todo.md, Task 30): each link hashes the previous hash and the canonical event; the first
broken link is found whether an event is changed, removed or reordered; the answers digest ignores storage order."""
import json

from zeka.modules.exam import domain


def chain(n=5, exam_id=7):
    out, prev = [], domain.GENESIS
    for seq in range(1, n + 1):
        data = {"i": seq, "note": "ə"}
        h = domain.link(prev, domain.canonical_event(exam_id, seq, "x.event", 1, 2, data, f"2026-11-19T06:0{seq}:00+00:00"))
        out.append({"exam_id": exam_id, "seq": seq, "kind": "x.event", "actor_id": 1, "student_id": 2, "data": json.dumps(data, ensure_ascii=False),
                    "at": f"2026-11-19T06:0{seq}:00+00:00", "prev_hash": prev, "hash": h})
        prev = h
    return out


def test_an_untouched_chain_holds():
    assert domain.chain_break(chain()) is None
    assert domain.chain_break([]) is None


def test_a_changed_event_breaks_its_own_link_even_the_last_one():
    for i in (0, 2, 4):
        evs = chain()
        evs[i]["data"] = json.dumps({"i": 99, "note": "ə"})
        assert domain.chain_break(evs) == {"seq": i + 1, "problem": "hash"}
    evs = chain()
    evs[4]["kind"] = "y.event"
    assert domain.chain_break(evs) == {"seq": 5, "problem": "hash"}


def test_a_removed_event_is_a_missing_seq_and_a_recomputed_one_breaks_the_next_link():
    evs = chain()
    del evs[2]
    assert domain.chain_break(evs) == {"seq": 3, "problem": "missing"}
    evs = chain()
    evs[1]["data"] = json.dumps({"i": 99})                      # changed and its own hash recomputed: the next link breaks
    evs[1]["hash"] = domain.link(evs[1]["prev_hash"], domain.canonical_event(7, 2, "x.event", 1, 2, {"i": 99}, evs[1]["at"]))
    assert domain.chain_break(evs) == {"seq": 3, "problem": "prev_hash"}


def test_the_first_link_starts_at_genesis():
    evs = chain()
    evs[0]["prev_hash"] = "1" * 64
    assert domain.chain_break(evs) == {"seq": 1, "problem": "prev_hash"}


def test_the_canonical_event_does_not_depend_on_key_order():
    a = domain.canonical_event(1, 1, "k", None, 3, {"b": 1, "a": [1, 2]}, "t")
    b = domain.canonical_event(1, 1, "k", None, 3, {"a": [1, 2], "b": 1}, "t")
    assert a == b and '"a":[1,2]' in a


def test_the_answers_digest_is_by_qid_and_sees_every_change():
    d = domain.answers_digest({5: '"x"', 2: '"1"'})
    assert d == domain.answers_digest({2: '"1"', 5: '"x"'})
    assert d != domain.answers_digest({2: '"1"', 5: '"y"'})
    assert d != domain.answers_digest({2: '"1"'})
    assert len(d) == 64
