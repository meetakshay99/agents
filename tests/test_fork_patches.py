"""Tests for the fork's own patches carried on top of upstream livekit/agents.

- sentence splitter (tokenize/_basic_sent.py): extra sentence terminators
- OpenAI Realtime ``vad_options`` (llm/_realtime/openai.py)
- Deepgram ``min_confidence_threshold`` (deepgram stt.py / stt_v2.py)
"""

from __future__ import annotations

import pytest
from openai.types.beta.realtime.session import TurnDetection

from livekit.agents.llm._realtime import openai_utils
from livekit.agents.tokenize import _basic_sent
from livekit.plugins.deepgram.stt import live_transcription_to_speech_data
from livekit.plugins.deepgram.stt_v2 import _parse_transcription
from livekit.plugins.openai import realtime

pytestmark = pytest.mark.unit


def _texts(text: str) -> list[str]:
    return [s for s, _, _ in _basic_sent.split_sentences(text, min_sentence_len=1)]


# --- sentence splitter -------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("यह पहला वाक्य है। यह दूसरा वाक्य है।", ["यह पहला वाक्य है।", "यह दूसरा वाक्य है।"]),
        ("প্রথম বাক্য। দ্বিতীয় বাক্য।", ["প্রথম বাক্য।", "দ্বিতীয় বাক্য।"]),
        ("श्लोक एक॥ श्लोक दो॥", ["श्लोक एक॥", "श्लोक दो॥"]),
        ("كيف حالك؟ أنا بخير.", ["كيف حالك؟", "أنا بخير."]),
        ("یہ پہلا جملہ ہے۔ یہ دوسرا ہے۔", ["یہ پہلا جملہ ہے۔", "یہ دوسرا ہے۔"]),
    ],
)
def test_splitter_non_latin_terminators(text: str, expected: list[str]) -> None:
    assert _texts(text) == expected


@pytest.mark.parametrize(
    "template",
    [
        "<speak>Hello{t}</speak> How are you{t}",
        'She said "fine{t}" Then left{t}',
        "First{t}<break time='1s'/> Second{t}",
        "One{t} Two{t} Three{t}",
    ],
)
@pytest.mark.parametrize("terminator", ["।", "॥", "؟", "۔"])
def test_splitter_new_terminators_behave_like_period(template: str, terminator: str) -> None:
    # the added terminators must split exactly where "." splits, tags and quotes included
    with_period = _texts(template.format(t="."))
    with_new = _texts(template.format(t=terminator))
    assert with_new == [s.replace(".", terminator) for s in with_period]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Hello there. How are you? I am fine!", ["Hello there.", "How are you?", "I am fine!"]),
        ("Version 1.5 is out. Try it.", ["Version 1.5 is out.", "Try it."]),
        ('He said "stop." Then he left.', ['He said "stop."', "Then he left."]),
    ],
)
def test_splitter_latin_unchanged(text: str, expected: list[str]) -> None:
    assert _texts(text) == expected


# --- OpenAI Realtime vad_options --------------------------------------------


def test_vad_options_without_turn_detection_selects_server_vad() -> None:
    model = realtime.RealtimeModel(
        api_key="test",
        vad_options={"threshold": 0.7, "prefix_padding_ms": 250, "silence_duration_ms": 600},
    )
    td = model._opts.turn_detection
    assert td is not None
    assert td.type == "server_vad"
    assert td.threshold == 0.7
    assert td.prefix_padding_ms == 250
    assert td.silence_duration_ms == 600
    assert td.create_response is True


def test_vad_options_does_not_mutate_default() -> None:
    realtime.RealtimeModel(api_key="test", vad_options={"threshold": 0.9})
    other = realtime.RealtimeModel(api_key="test")
    assert other._opts.turn_detection == openai_utils.DEFAULT_TURN_DETECTION
    assert openai_utils.DEFAULT_TURN_DETECTION.type == "semantic_vad"


def test_vad_options_override_copy_of_explicit_turn_detection() -> None:
    explicit = TurnDetection(type="server_vad", threshold=0.3, silence_duration_ms=200)
    model = realtime.RealtimeModel(
        api_key="test", turn_detection=explicit, vad_options={"threshold": 0.8}
    )
    assert model._opts.turn_detection.threshold == 0.8
    assert model._opts.turn_detection.silence_duration_ms == 200
    assert explicit.threshold == 0.3


def test_no_vad_options_keeps_default() -> None:
    model = realtime.RealtimeModel(api_key="test")
    assert model._opts.turn_detection == openai_utils.DEFAULT_TURN_DETECTION


# --- Deepgram min_confidence_threshold ---------------------------------------


def _v1_payload(confidence: float) -> dict:
    return {
        "channel": {
            "alternatives": [
                {
                    "transcript": "hello",
                    "confidence": confidence,
                    "words": [{"word": "hello", "start": 0.1, "end": 0.5, "confidence": confidence}],
                }
            ]
        }
    }


@pytest.mark.parametrize(
    "kwargs, confidence, kept",
    [
        ({}, 0.1, True),  # threshold omitted: no filtering
        ({"min_confidence_threshold": None}, 0.1, True),
        ({"min_confidence_threshold": 0.4}, 0.39, False),
        ({"min_confidence_threshold": 0.4}, 0.4, True),  # boundary is inclusive
        ({"min_confidence_threshold": 0.4}, 0.9, True),
    ],
)
def test_deepgram_v1_threshold(kwargs: dict, confidence: float, kept: bool) -> None:
    data = live_transcription_to_speech_data(
        "en", _v1_payload(confidence), is_final=True, start_time_offset=0.0, **kwargs
    )
    assert (len(data) == 1) is kept


@pytest.mark.parametrize(
    "threshold, confidence, kept",
    [(None, 0.1, True), (0.4, 0.39, False), (0.4, 0.4, True)],
)
def test_deepgram_flux_threshold(threshold: float | None, confidence: float, kept: bool) -> None:
    from livekit.agents.types import NOT_GIVEN

    data = {
        "transcript": "hello",
        "words": [{"word": "hello", "start": 0.1, "end": 0.5, "confidence": confidence}],
    }
    result = _parse_transcription("en", data, NOT_GIVEN if threshold is None else threshold, 0.0)
    assert (len(result) == 1) is kept
