from datetime import UTC, datetime

import pytest
from meritum_core.checks.ocr import MAX_IMAGE_BYTES
from meritum_core.shared.blobs import BlobKind
from tests.checks.test_uploads import Blobs, BrokenBlobs, client_on

from meritum_backend.checks.constants import IMAGE_RETENTION

PNG = b"\x89PNG\r\n\x1a\n" + bytes(16)
JPEG = b"\xff\xd8\xff\xe0" + bytes(16)
WEBP = b"RIFF" + bytes(4) + b"WEBP" + bytes(8)


@pytest.mark.parametrize(
    ("data", "content_type"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")],
)
def test_image_is_kept_for_the_check_retention(data: bytes, content_type: str) -> None:
    blobs = Blobs()
    sent = datetime.now(UTC)
    response = client_on(blobs).post(
        "/api/v1/images", content=data, headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 201
    [ref] = blobs.refs
    assert response.json() == {"image_id": ref.blob_id}
    assert ref.blob_id.startswith("image_")
    assert ref.kind == BlobKind.IMAGE
    assert ref.content_type == content_type  # from the bytes, not the header
    assert sent + IMAGE_RETENTION <= ref.expires_at


def test_unsupported_format_is_out_of_scope_and_stores_nothing() -> None:
    blobs = Blobs()
    response = client_on(blobs).post("/api/v1/images", content=b"GIF89a....")
    assert response.status_code == 415
    body = response.json()
    assert body["status"] == "out_of_scope"
    assert body["message_key"] == "out_of_scope_code.image"
    assert body["formats"] == ["PNG", "JPEG", "WebP"]
    assert blobs.refs == []


def test_oversize_is_413_without_a_verdict() -> None:
    blobs = Blobs()
    response = client_on(blobs).post(
        "/api/v1/images", content=PNG + bytes(MAX_IMAGE_BYTES)
    )
    assert response.status_code == 413
    assert response.json()["status"] == "out_of_scope"
    assert response.json()["max_mb"] == 10
    assert blobs.refs == []


def test_storage_failure_is_503_without_details() -> None:
    response = client_on(BrokenBlobs()).post("/api/v1/images", content=PNG)
    assert response.status_code == 503
    assert "disk" not in response.text
