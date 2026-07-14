from redis import RedisError

from src.cache import tickets as ticket_cache
from src.models import Ticket
from src.services import tickets as ticket_service


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex):
        self.values[key] = value.encode("utf-8")
        self.ttls[key] = ex
        return True

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)


def _api_ticket(make_ticket):
    return Ticket(**vars(make_ticket()))


def test_ticket_cache_miss_write_and_hit(monkeypatch, make_ticket):
    redis = FakeRedis()
    ticket = _api_ticket(make_ticket)
    monkeypatch.setattr(ticket_cache, "get_redis_client", lambda: redis)

    assert ticket_cache.check_ticket(ticket.id) is None
    assert ticket_cache.cache_ticket(ticket) is True

    cached_ticket = ticket_cache.check_ticket(ticket.id)
    assert cached_ticket == ticket
    assert redis.ttls["ticket:ticket-1"] == 300


def test_ticket_cache_miss_after_expiry_returns_none(monkeypatch, make_ticket):
    redis = FakeRedis()
    ticket = _api_ticket(make_ticket)
    monkeypatch.setattr(ticket_cache, "get_redis_client", lambda: redis)
    ticket_cache.cache_ticket(ticket)

    redis.values.clear()  # Redis has expired the key.

    assert ticket_cache.check_ticket(ticket.id) is None


def test_ticket_cache_delete_invalidates_a_cached_ticket(monkeypatch, make_ticket):
    redis = FakeRedis()
    ticket = _api_ticket(make_ticket)
    monkeypatch.setattr(ticket_cache, "get_redis_client", lambda: redis)
    ticket_cache.cache_ticket(ticket)

    assert ticket_cache.delete_ticket(ticket.id) is True
    assert ticket_cache.check_ticket(ticket.id) is None


def test_ticket_cache_outage_fails_open_and_logs(monkeypatch, make_ticket, caplog):
    ticket = _api_ticket(make_ticket)

    class BrokenRedis:
        def get(self, _):
            raise RedisError("read unavailable")

        def set(self, *_args, **_kwargs):
            raise RedisError("write unavailable")

        def delete(self, _):
            raise RedisError("delete unavailable")

    monkeypatch.setattr(ticket_cache, "get_redis_client", lambda: BrokenRedis())

    assert ticket_cache.check_ticket(ticket.id) is None
    assert ticket_cache.cache_ticket(ticket) is False
    assert ticket_cache.delete_ticket(ticket.id) is False
    assert "Ticket cache read failed" in caplog.text
    assert "Ticket cache write failed" in caplog.text
    assert "Ticket cache delete failed" in caplog.text


def test_ticket_service_uses_database_only_after_a_cache_miss(
    monkeypatch, make_user, make_ticket
):
    requester = make_user()
    database_ticket = make_ticket(creator_user_id=requester.id)
    cached = []

    monkeypatch.setattr(ticket_service, "check_cached_ticket", lambda _: None)
    monkeypatch.setattr(ticket_service.operations, "get_ticket", lambda _: database_ticket)
    monkeypatch.setattr(ticket_service, "cache_ticket", lambda ticket: cached.append(ticket) or True)

    result = ticket_service.get_ticket(database_ticket.id, requester)

    assert result.id == database_ticket.id
    assert [ticket.id for ticket in cached] == [database_ticket.id]


def test_ticket_service_cache_hit_skips_database_and_cache_write(
    monkeypatch, make_user, make_ticket
):
    requester = make_user()
    cached_ticket = _api_ticket(lambda: make_ticket(creator_user_id=requester.id))

    monkeypatch.setattr(ticket_service, "check_cached_ticket", lambda _: cached_ticket)
    monkeypatch.setattr(
        ticket_service.operations,
        "get_ticket",
        lambda _: (_ for _ in ()).throw(AssertionError("database must not be queried")),
    )
    monkeypatch.setattr(
        ticket_service,
        "cache_ticket",
        lambda _: (_ for _ in ()).throw(AssertionError("cache must not be rewritten")),
    )

    assert ticket_service.get_ticket(cached_ticket.id, requester).id == cached_ticket.id


def test_ticket_update_invalidates_its_cache_entry(monkeypatch, make_user, make_ticket):
    requester = make_user(role=ticket_service.constants.Role.MANAGER)
    ticket = make_ticket()
    invalidated_ids = []

    monkeypatch.setattr(ticket_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(ticket_service.operations, "update_ticket", lambda *_: ticket)
    monkeypatch.setattr(
        ticket_service, "delete_cached_ticket", lambda ticket_id: invalidated_ids.append(ticket_id) or True
    )

    ticket_service.update_ticket(
        ticket.id,
        ticket_service.api_models.TicketUpdate(priority=ticket_service.constants.Priority.HIGH),
        requester,
    )

    assert invalidated_ids == [ticket.id]


def test_ticket_claim_invalidates_its_cache_entry(monkeypatch, make_user, make_ticket):
    requester = make_user(id="agent-1", role=ticket_service.constants.Role.AGENT)
    ticket = make_ticket()
    invalidated_ids = []

    monkeypatch.setattr(ticket_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(ticket_service.operations, "claim_ticket", lambda *_: ticket)
    monkeypatch.setattr(
        ticket_service, "delete_cached_ticket", lambda ticket_id: invalidated_ids.append(ticket_id) or True
    )

    ticket_service.claim_ticket(ticket.id, requester)

    assert invalidated_ids == [ticket.id]


def test_ticket_assignment_invalidates_its_cache_entry(monkeypatch, make_user, make_ticket):
    requester = make_user(id="manager-1", role=ticket_service.constants.Role.MANAGER)
    agent = make_user(id="agent-1", role=ticket_service.constants.Role.AGENT)
    ticket = make_ticket()
    invalidated_ids = []

    monkeypatch.setattr(ticket_service.operations, "get_ticket", lambda _: ticket)
    monkeypatch.setattr(ticket_service.operations, "get_user", lambda _: agent)
    monkeypatch.setattr(ticket_service.operations, "assign_ticket", lambda *_: ticket)
    monkeypatch.setattr(
        ticket_service, "delete_cached_ticket", lambda ticket_id: invalidated_ids.append(ticket_id) or True
    )

    ticket_service.assign_ticket(ticket.id, agent.id, requester)

    assert invalidated_ids == [ticket.id]
