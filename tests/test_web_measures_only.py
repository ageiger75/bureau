"""The cockpit measures; it does not track (decided by the reader on 9 November 2026).

Commitments, conclusions on a subject, questions and decisions live in the reader's
cabinet, outside this repository. The screens therefore offer no gesture that writes: no
form, and no route that takes a pledge, carries a reading, accepts a gap or closes a
subject. The register and the pledges table left the repository on 13 November 2026, once
the cabinet had taken them over. These tests guard the boundary.
"""

from __future__ import annotations

SCREENS = ("/", "/analyses", "/perimetres", "/marches", "/marche/china", "/system")


def test_no_screen_offers_a_form(client):
    for path in SCREENS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "<form" not in response.text, path


def test_the_routes_that_wrote_are_gone(client):
    for path in ("/engagements", "/engagements/ENG-001/update", "/issues/ISS-001/read",
                 "/issues/ISS-001/accept", "/issues/ISS-001/close"):
        response = client.post(path, data={"action": "x"}, follow_redirects=False)
        assert response.status_code == 404, (path, response.status_code)
