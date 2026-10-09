import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

Post = Callable[[str, dict, dict], dict]


def http_post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


@dataclass(frozen=True)
class Question:
    name: str
    instructions: str
    choices: dict[str, str]


class Decider(Protocol):
    name: str

    def decide(self, text: str, question: Question) -> dict[str, float]: ...


def _systemone_body(model: str, text: str, question: Question) -> dict:
    return {
        "model": model,
        "state": text,
        "questions": {
            question.name: {
                "type": "choice",
                "instructions": question.instructions,
                "criteria": question.choices,
            }
        },
    }


def _systemone_probabilities(answers: dict, question: Question) -> dict[str, float]:
    answer = answers[question.name]
    scores = answer[answer["type"]]
    return {value: float(scores.get(value, 0.0)) for value in question.choices}


class ClefDecider:
    def __init__(self, account_id: str, token: str, model: str = "clef", post: Post = http_post):
        self.name = model
        self.url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}"
        self.token = token
        self.model = model
        self.post = post

    def decide(self, text: str, question: Question) -> dict[str, float]:
        res = self.post(
            self.url,
            {"Authorization": f"Bearer {self.token}"},
            _systemone_body(self.model, text, question),
        )
        return _systemone_probabilities(res["result"]["answers"], question)


class JevDecider:
    def __init__(self, api_key: str, model: str = "jev-latest", post: Post = http_post):
        self.name = "jev"
        self.api_key = api_key
        self.model = model
        self.post = post

    def decide(self, text: str, question: Question) -> dict[str, float]:
        res = self.post(
            "https://api.typesafe.ai/v1/systemone",
            {"Authorization": f"Bearer {self.api_key}"},
            _systemone_body(self.model, text, question),
        )
        return _systemone_probabilities(res["answers"], question)


class OpenAIDecider:
    def __init__(self, api_key: str, model: str = "gpt-6-luna", post: Post = http_post):
        self.name = model
        self.api_key = api_key
        self.model = model
        self.post = post

    def decide(self, text: str, question: Question) -> dict[str, float]:
        res = self.post(
            "https://api.openai.com/v1/decisions",
            {"Authorization": f"Bearer {self.api_key}"},
            {
                "model": self.model,
                "input": text,
                "questions": [
                    {
                        "type": "choice",
                        "name": question.name,
                        "instructions": question.instructions,
                        "choices": [{"value": v, "description": d} for v, d in question.choices.items()],
                    }
                ],
            },
        )
        answer = next(a for a in res["answers"] if a["name"] == question.name)
        scores = {p["value"]: float(p["probability"]) for p in answer["probabilities"]}
        return {value: scores.get(value, 0.0) for value in question.choices}
