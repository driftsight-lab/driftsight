"""속성 매핑 — 본문 크기 상한·문서 단위 제외·금지 속성 미기록 (telemetry.md > 4.3 · 4.4)."""

import json

from src.sdk.attributes import (
    ANSWER_MAX_BYTES,
    CONTENT_ANSWER,
    CONTENT_CONTEXTS,
    CONTENT_QUESTION,
    CONTEXTS_MAX_BYTES,
    QUESTION_MAX_BYTES,
    content_attributes,
    contexts_attributes,
    sanitize,
    truncate_utf8,
    version_attributes,
)


def test_truncate_keeps_multibyte_characters_whole() -> None:
    text, cut = truncate_utf8("가나다", 4)  # 한 글자 3바이트

    assert (text, cut) == ("가", True)


def test_question_over_limit_is_truncated_and_flagged() -> None:
    attrs = content_attributes("q" * (QUESTION_MAX_BYTES + 10), "a")

    assert len(str(attrs[CONTENT_QUESTION])) == QUESTION_MAX_BYTES
    assert attrs[f"{CONTENT_QUESTION}_truncated"] is True
    assert f"{CONTENT_ANSWER}_truncated" not in attrs


def test_answer_none_is_not_recorded() -> None:
    attrs = content_attributes("q", None)

    assert CONTENT_ANSWER not in attrs


def test_answer_limit() -> None:
    attrs = content_attributes("q", "a" * (ANSWER_MAX_BYTES + 1))

    assert attrs[f"{CONTENT_ANSWER}_truncated"] is True


def test_contexts_dropped_by_document_from_the_end() -> None:
    doc = {"id": "d", "text": "x" * (CONTEXTS_MAX_BYTES // 3)}
    attrs = contexts_attributes([doc, doc, doc, doc])

    kept = json.loads(str(attrs[CONTENT_CONTEXTS]))
    assert len(kept) < 4
    assert all(d == doc for d in kept)  # 문서를 중간에서 자르지 않는다
    assert attrs[f"{CONTENT_CONTEXTS}_truncated"] is True


def test_version_attributes_carry_name_and_id() -> None:
    attrs = version_attributes(
        prompt="p-v1", model="m-v1", retrieval="r-v1", prompt_id=1, model_id=2, retrieval_id=3
    )

    assert attrs["app.version.prompt"] == "p-v1"
    assert attrs["app.version.retrieval_id"] == 3


def test_sanitize_drops_forbidden_keys_and_none() -> None:
    attrs = sanitize(
        {
            "gen_ai.request.model": "claude",
            "app.anthropic_api_key": "sk-x",
            "http.request.header.authorization": "Bearer x",
            "exception.message": "contains user text",
            "exception.type": "TimeoutError",
            "app.slack.webhook_url": "https://hooks",
            "gen_ai.request.temperature": None,
        }
    )

    assert attrs == {"gen_ai.request.model": "claude", "exception.type": "TimeoutError"}


def test_sanitize_keeps_token_counts_but_drops_credential_tokens() -> None:
    attrs = sanitize(
        {
            "gen_ai.usage.input_tokens": 1,
            "gen_ai.usage.output_tokens": 2,
            "gen_ai.request.max_tokens": 256,
            "app.session_token": "x",
            "http.access-token": "y",
        }
    )

    assert attrs == {
        "gen_ai.usage.input_tokens": 1,
        "gen_ai.usage.output_tokens": 2,
        "gen_ai.request.max_tokens": 256,
    }
