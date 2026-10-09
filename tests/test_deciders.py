from masuda_verdict.deciders import ClefDecider, JevDecider, OpenAIDecider, Question

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
    post = FakePost({"result": {"answers": {"verdict": {"type": "choice", "choice": {"fact": 1.0}}}}, "success": True})
    ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
    assert post.calls[0][0] == "https://api.cloudflare.com/client/v4/accounts/acc/ai/run/@cf/cloudflare/clef"


def test_clef_sends_question_as_criteria():
    post = FakePost({"result": {"answers": {"verdict": {"type": "choice", "choice": {"fact": 1.0}}}}, "success": True})
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
                "answers": {"verdict": {"type": "choice", "choice": {"fishing": 0.1, "fiction": 0.7, "fact": 0.2}}}
            },
            "success": True,
        }
    )
    probs = ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
    assert probs == {"fishing": 0.1, "fiction": 0.7, "fact": 0.2}


def test_clef_fills_missing_choices_with_zero():
    post = FakePost({"result": {"answers": {"verdict": {"type": "choice", "choice": {"fact": 1.0}}}}, "success": True})
    probs = ClefDecider(account_id="acc", token="tok", post=post).decide("本文", QUESTION)
    assert probs == {"fishing": 0.0, "fiction": 0.0, "fact": 1.0}


def test_jev_reads_answers_at_root():
    post = FakePost(
        {
            "model": "jev-1.13.0",
            "answers": {"verdict": {"type": "choice", "choice": {"fishing": 0.9, "fiction": 0.1, "fact": 0.0}}},
        }
    )
    probs = JevDecider(api_key="k", post=post).decide("本文", QUESTION)
    assert probs == {"fishing": 0.9, "fiction": 0.1, "fact": 0.0}


def test_jev_posts_to_systemone():
    post = FakePost({"answers": {"verdict": {"type": "choice", "choice": {"fact": 1.0}}}})
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
