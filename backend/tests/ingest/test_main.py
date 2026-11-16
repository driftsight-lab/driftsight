"""Ingest router — 출처 헤더·본문 검증·배치 상한 (DB 불필요), 오류 본문 내부 정보 미노출."""

import uuid

import httpx
import pytest

from src.ingest.main import create_app
from tests.ingest.otlp_factory import payload, rag_trace


class _NoDb:
    """검증 단계에서 거부되면 DB에 닿지 않아야 한다."""

    def __call__(self) -> object:
        raise AssertionError("DB must not be touched")


async def _post(
    json_body: object = None, *, headers: dict[str, str] | None = None, content: bytes | None = None
) -> httpx.Response:
    app = create_app(_NoDb())  # type: ignore[arg-type]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ingest") as http:
        return await http.post(
            "/internal/v1/traces",
            json=json_body if content is None else None,
            content=content,
            headers=headers if headers is not None else {"X-Ingest-Source": "collector"},
        )


@pytest.mark.asyncio
async def test_missing_source_header_is_403() -> None:
    resp = await _post(payload(rag_trace()), headers={})

    assert resp.status_code == 403
    assert resp.json() == {"error": "FORBIDDEN"}


@pytest.mark.asyncio
async def test_invalid_json_is_400_without_details() -> None:
    resp = await _post(
        content=b"{not json",
        headers={"X-Ingest-Source": "collector", "Content-Type": "application/json"},
    )

    assert resp.status_code == 400
    assert resp.json() == {"error": "INVALID_REQUEST"}


@pytest.mark.asyncio
async def test_batch_over_500_traces_is_400() -> None:
    spans = [s for _ in range(501) for s in rag_trace(uuid.uuid4().hex)[:1]]

    resp = await _post(payload(spans))

    assert resp.status_code == 400
