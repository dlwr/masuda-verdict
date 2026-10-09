import io
import urllib.error

import pytest

from masuda_verdict import deciders
from masuda_verdict.deciders import Budgeted, CarryOver, ClefDecider, JevDecider, OpenAIDecider, Question

QUESTION = Question(
    name="verdict",
    instructions="この文章は釣り・創作・事実のどれか",
    choices={"fishing": "釣り", "fiction": "創作", "fact": "事実"},
)


class FakePost:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.response


def test_clef_posts_to_workers_ai_run_endpoint():
    post = FakePost(
        {
            "result": {
                "answers": {
                    "verdict": {"type": "choice", "choice": "x", "probabilities": {"fact": 1.0}, "confidence": 0.5}
                }
            },
            "success": True,
        }
    )
    ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
    assert post.calls[0][0] == "https://api.cloudflare.com/client/v4/accounts/acc/ai/run/@cf/cloudflare/clef"


def test_clef_sends_question_as_criteria():
    post = FakePost(
        {
            "result": {
                "answers": {
                    "verdict": {"type": "choice", "choice": "x", "probabilities": {"fact": 1.0}, "confidence": 0.5}
                }
            },
            "success": True,
        }
    )
    ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
    assert post.calls[0][2] == {
        "model": "clef",
        "state": "本文",
        "questions": {
            "verdict": {
                "type": "choice",
                "instructions": "この文章は釣り・創作・事実のどれか",
                "criteria": {"fishing": "釣り", "fiction": "創作", "fact": "事実"},
            }
        },
    }


def test_clef_unwraps_result_into_probabilities():
    post = FakePost(
        {
            "result": {
                "answers": {
                    "verdict": {
                        "type": "choice",
                        "choice": "x",
                        "probabilities": {"fishing": 0.1, "fiction": 0.7, "fact": 0.2},
                        "confidence": 0.5,
                    }
                }
            },
            "success": True,
        }
    )
    probs = ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
    assert probs == {"fishing": 0.1, "fiction": 0.7, "fact": 0.2}


def test_clef_fills_missing_choices_with_zero():
    post = FakePost(
        {
            "result": {
                "answers": {
                    "verdict": {"type": "choice", "choice": "x", "probabilities": {"fact": 1.0}, "confidence": 0.5}
                }
            },
            "success": True,
        }
    )
    probs = ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
    assert probs == {"fishing": 0.0, "fiction": 0.0, "fact": 1.0}


def test_jev_reads_answers_at_root():
    post = FakePost(
        {
            "model": "jev-1.13.0",
            "answers": {
                "verdict": {
                    "type": "choice",
                    "choice": "x",
                    "probabilities": {"fishing": 0.9, "fiction": 0.1, "fact": 0.0},
                    "confidence": 0.5,
                }
            },
        }
    )
    probs = JevDecider(api_key="k", post=post).decide("本文", QUESTION)
    assert probs == {"fishing": 0.9, "fiction": 0.1, "fact": 0.0}


def test_jev_posts_to_systemone():
    post = FakePost(
        {"answers": {"verdict": {"type": "choice", "choice": "x", "probabilities": {"fact": 1.0}, "confidence": 0.5}}}
    )
    JevDecider(api_key="k", post=post).decide("本文", QUESTION)
    assert post.calls[0][0] == "https://api.typesafe.ai/v1/systemone"


def test_openai_sends_questions_as_array():
    post = FakePost(
        {
            "answers": [
                {
                    "name": "verdict",
                    "type": "choice",
                    "choice": "fact",
                    "probabilities": [{"value": "fact", "probability": 1.0}],
                }
            ]
        }
    )
    OpenAIDecider(api_key="k", post=post).decide("本文", QUESTION)
    assert post.calls[0][2]["questions"] == [
        {
            "type": "choice",
            "name": "verdict",
            "instructions": "この文章は釣り・創作・事実のどれか",
            "choices": [
                {"value": "fishing", "description": "釣り"},
                {"value": "fiction", "description": "創作"},
                {"value": "fact", "description": "事実"},
            ],
        }
    ]


def test_openai_reads_probabilities_list():
    post = FakePost(
        {
            "answers": [
                {
                    "name": "verdict",
                    "type": "choice",
                    "choice": "fiction",
                    "probabilities": [
                        {"value": "fishing", "probability": 0.05},
                        {"value": "fiction", "probability": 0.9},
                        {"value": "fact", "probability": 0.05},
                    ],
                    "confidence": 0.9,
                }
            ]
        }
    )
    probs = OpenAIDecider(api_key="k", post=post).decide("本文", QUESTION)
    assert probs == {"fishing": 0.05, "fiction": 0.9, "fact": 0.05}


def raise_http(code):
    def urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, code, "error", {}, io.BytesIO(b"{}"))

    return urlopen


def test_http_post_turns_429_into_carry_over(monkeypatch):
    monkeypatch.setattr(deciders.urllib.request, "urlopen", raise_http(429))
    with pytest.raises(CarryOver):
        deciders.http_post("https://example.com", {}, {})


def test_http_post_keeps_other_http_errors(monkeypatch):
    monkeypatch.setattr(deciders.urllib.request, "urlopen", raise_http(400))
    with pytest.raises(urllib.error.HTTPError):
        deciders.http_post("https://example.com", {}, {})


class CountingDecider:
    name = "clef"

    def decide(self, text, question):
        return {"fact": 1.0}


def test_budgeted_keeps_inner_name():
    assert Budgeted(CountingDecider(), limit=1).name == "clef"


def test_budgeted_allows_calls_up_to_limit():
    d = Budgeted(CountingDecider(), limit=2)
    assert [d.decide("t", QUESTION), d.decide("t", QUESTION)] == [{"fact": 1.0}, {"fact": 1.0}]


def test_budgeted_carries_over_beyond_limit():
    d = Budgeted(CountingDecider(), limit=1)
    d.decide("t", QUESTION)
    with pytest.raises(CarryOver):
        d.decide("t", QUESTION)


def test_clef_reports_unexpected_answer_shape():
    post = FakePost({"result": {"answers": {"verdict": {"type": "choice", "choice": "fact"}}}, "success": True})
    with pytest.raises(ValueError, match='"choice": "fact"'):
        ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
