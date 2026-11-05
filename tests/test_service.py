from __future__ import annotations

import pytest

from app.database import LAB_PASSWORD
from app.service import LabError, LabService


def test_synthetic_session_authentication_and_revocation(service: LabService) -> None:
    assert service.create_session("alice", "wrong-password") is None
    session = service.create_session("alice", LAB_PASSWORD)
    assert session is not None
    assert service.authenticate(session["session_token"]) == "alice"
    service.revoke_session(session["session_token"])
    assert service.authenticate(session["session_token"]) is None


def test_race_has_exactly_one_winner(service: LabService) -> None:
    result = service.simulate_race("race_test", 16)
    assert result["successful_claims"] == 1
    assert result["invariant_preserved"] is True
    owners = [
        row["owner"] for row in service.list_usernames() if row["name"] == "race_test"
    ]
    assert owners == [result["winner"]]


def test_released_name_observes_cooldown(service: LabService) -> None:
    released = service.release("nova", "alice")
    assert released["status"] == "released"
    blocked = service.claim("nova", "bob")
    assert blocked["status"] == "cooldown"
    assert blocked["available_at"] == released["available_at"]

    service.set_defenses(False)
    assert service.claim("nova", "bob")["status"] == "claimed"


def test_transfer_is_direct_and_has_no_availability_gap(service: LabService) -> None:
    result = service.transfer("nova", "alice", "bob")
    assert result == {
        "status": "transferred",
        "name": "nova",
        "source": "alice",
        "target": "bob",
        "version": 2,
        "availability_gap": False,
    }
    row = next(row for row in service.list_usernames() if row["name"] == "nova")
    assert row["owner"] == "bob"
    with pytest.raises(LabError):
        service.transfer("nova", "alice", "carol")


def test_only_owner_can_release(service: LabService) -> None:
    with pytest.raises(LabError, match="current owner"):
        service.release("nova", "bob")


def test_burst_rate_limit_and_comparison_mode(service: LabService) -> None:
    protected = service.simulate_burst("alice", 12, "burst_test")
    assert protected["outcomes"] == {"claimed": 1, "taken": 4, "rate_limited": 7}
    assert protected["detection_effective"] is True

    service.set_defenses(False)
    comparison = service.simulate_burst("alice", 12, "burst_test")
    assert comparison["outcomes"] == {"claimed": 1, "taken": 11}
    assert comparison["detection_effective"] is None


def test_invalid_names_and_accounts_are_rejected(service: LabService) -> None:
    with pytest.raises(LabError):
        service.claim("../invalid", "alice")
    with pytest.raises(LabError, match="Unknown synthetic account"):
        service.claim("valid_name", "not_a_fixture")


def test_reset_restores_deterministic_fixtures(service: LabService) -> None:
    service.transfer("nova", "alice", "bob")
    service.db.reset()
    row = next(row for row in service.list_usernames() if row["name"] == "nova")
    assert row["owner"] == "alice"
    assert service.defenses_enabled() is True
