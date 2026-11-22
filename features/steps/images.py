"""Steps for POST /api/v1/images (checks.feature): upload, then check by image_id.

The app runs with core's in-memory BlobStore and InMemoryJobQueue, so no disk,
bucket or database.
"""

import asyncio
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from features.steps.audio import SESSION, SESSION_HEADER, prepare

PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)
GIF = b"GIF89a" + bytes(32)


@given("plik PNG ze zrzutem ekranu posta")
def png_file(context: Context) -> None:
    """A screenshot from the web form.

    Args:
        context: the behave context.

    Features:
        US-SPR-08, F-33
    """
    prepare(context, PNG, "image/png")


@given("plik GIF zamiast zrzutu ekranu")
def gif_file(context: Context) -> None:
    """An image of a format OCR does not read.

    Args:
        context: the behave context.

    Features:
        US-SPR-08, F-33
    """
    prepare(context, GIF, "image/gif")


@when("klient wysyła POST /api/v1/images")
def post_image(context: Context) -> None:
    """Send the file as the request body.

    Args:
        context: the behave context; gets ``response``.

    Features:
        US-SPR-08, F-33
    """
    data, content_type = context.audio
    context.response = context.client.post(
        "/api/v1/images", content=data, headers={"Content-Type": content_type}
    )


@then("odpowiedź ma kod 201 i image_id")
def image_stored(context: Context) -> None:
    """The file is in the BlobStore under the returned id.

    Args:
        context: the behave context; gets ``image_id``.

    Features:
        US-SPR-08, F-33
    """
    assert context.response.status_code == HTTPStatus.CREATED
    context.image_id = context.response.json()["image_id"]
    assert context.image_id.startswith("image_")
    assert asyncio.run(context.blobs.get(context.image_id)) == context.audio[0]


@then("POST /api/v1/checks z tym image_id startuje sprawdzenie")
def check_by_image_id(context: Context) -> None:
    """The check is accepted and the job carries the image id.

    Args:
        context: the behave context with ``client``, ``jobs`` and ``image_id``.

    Features:
        US-SPR-08, F-33
    """
    body = {"channel": "web", "image_id": context.image_id}
    response = context.client.post(
        "/api/v1/checks", json=body, headers={SESSION_HEADER: SESSION}
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    [job] = context.jobs.enqueued
    assert job.payload.request.image_id == context.image_id


@then('wynik ma stan "{state}" z komunikatem, jakie obrazy można wysłać')
def unsupported_image(context: Context, state: str) -> None:
    """Rejected as out of scope with the formats hint; nothing stored.

    Args:
        context: the behave context with ``response`` and ``blobs``.
        state: the expected check status.

    Features:
        US-SPR-08, F-33
    """
    assert context.response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    body = context.response.json()
    assert body["status"] == state
    assert body["message_key"] == "out_of_scope_code.image"
    assert body["formats"] == ["PNG", "JPEG", "WebP"]
    assert context.blobs.stored == []
