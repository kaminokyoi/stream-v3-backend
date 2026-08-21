"""Tests for the media proxy view (logo serving with forced Content-Type)."""
import io
from unittest import mock

import pytest
from django.core.files.storage import default_storage


@pytest.mark.django_db
def test_media_serves_svg_with_svg_content_type(api_client):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with mock.patch.object(default_storage, 'open', return_value=io.BytesIO(svg)):
        resp = api_client.get('/api/v1/public/media/logos/netflix/netflix_logo.svg')
    assert resp.status_code == 200
    assert resp['Content-Type'] == 'image/svg+xml'
    assert resp['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert b''.join(resp.streaming_content) == svg


@pytest.mark.django_db
def test_media_serves_png_with_mimetype(api_client):
    with mock.patch.object(default_storage, 'open', return_value=io.BytesIO(b'png')):
        resp = api_client.get('/api/v1/public/media/logos/spotify/spotify_logo.png')
    assert resp.status_code == 200
    assert resp['Content-Type'] == 'image/png'


@pytest.mark.django_db
def test_media_rejects_non_logo_prefix(api_client):
    with mock.patch.object(default_storage, 'open') as open_mock:
        resp = api_client.get('/api/v1/public/media/proofs/secret.png')
    assert resp.status_code == 404
    open_mock.assert_not_called()


@pytest.mark.django_db
def test_media_rejects_missing_file(api_client):
    with mock.patch.object(default_storage, 'open', side_effect=FileNotFoundError):
        resp = api_client.get('/api/v1/public/media/logos/netflix/netflix_logo.svg')
    assert resp.status_code == 404
