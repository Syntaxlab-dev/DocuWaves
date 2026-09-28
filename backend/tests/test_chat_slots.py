"""The ceiling on questions waiting on the model at once.

Each question can hold a worker thread for the whole chat timeout. Without a
ceiling a burst of slow answers takes every thread and the instance stops
answering anything, its health check included.
"""
import threading

import pytest

from app.services import doc_chat


@pytest.fixture
def two_slots(monkeypatch):
    monkeypatch.setattr(doc_chat, "_answer_slots", threading.BoundedSemaphore(2))


def test_a_slot_is_given_while_one_is_free(two_slots):
    with doc_chat.answer_slot() as got:
        assert got is True


def test_the_next_question_is_turned_away_when_all_are_taken(two_slots):
    with doc_chat.answer_slot() as first, doc_chat.answer_slot() as second:
        assert first and second
        with doc_chat.answer_slot() as third:
            assert third is False


def test_a_slot_is_given_back_even_when_the_answer_fails(two_slots):
    for _ in range(3):
        with pytest.raises(RuntimeError):
            with doc_chat.answer_slot() as got:
                assert got
                raise RuntimeError("model went away")
    with doc_chat.answer_slot() as first, doc_chat.answer_slot() as second:
        assert first and second


def test_turning_a_question_away_gives_back_nothing_it_did_not_take(two_slots):
    with doc_chat.answer_slot() as first, doc_chat.answer_slot() as second:
        for _ in range(5):
            with doc_chat.answer_slot() as refused:
                assert refused is False
    # BoundedSemaphore raises on a release beyond its size, so reaching this
    # line means no refused call released a slot it never held.
    with doc_chat.answer_slot() as again:
        assert again
