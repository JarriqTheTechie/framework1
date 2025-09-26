# lib/domain/event_bus.py
import json
from collections import defaultdict
from datetime import datetime
from typing import Callable, Type, Any

from lib.services.DomainEventOutbox import DomainEventOutbox

class DomainEventBus:
    _subscribers: dict[Type, list[Callable]] = defaultdict(list)

    @classmethod
    def subscribe(cls, event_type: Type, handler: Callable[[Any], None]):
        cls._subscribers[event_type].append(handler)

    @classmethod
    def publish(cls, event: Any, persist: bool = True):
        """
        Publish event to subscribers, persist in outbox for replay.
        """
        if persist:
            DomainEventOutbox.create(
                event_type=event.__class__.__name__,
                payload=json.dumps(event.__dict__, default=str)
            )

        # immediate in-memory dispatch (optional)
        for handler in cls._subscribers[type(event)]:
            try:
                handler(event)
            except Exception as e:
                print(f"[DomainEvent Error] {handler} failed: {e}")

    @classmethod
    def replay_outbox(cls, max_retries: int = 5):
        """
        Replay all unprocessed events from Outbox.
        """
        events = DomainEventOutbox().where_null_published_at().all()

        for outbox_event in events:
            try:
                payload = json.loads(outbox_event.payload)
                ev_cls = next((et for et in cls._subscribers if et.__name__ == outbox_event.event_type), None)
                if not ev_cls:
                    continue

                event = ev_cls(**payload)

                # Execute all handlers
                for handler in cls._subscribers[ev_cls]:
                    handler(event)

                # ✅ Success → mark published
                outbox_event.update({"published_at": datetime.utcnow().isoformat()})

            except Exception as e:
                print(f"[Outbox Replay Error] {e}")

                # ⏳ Retry logic
                retry_count = (outbox_event.retry_count or 0) + 1
                update_data = {"retry_count": retry_count}

                if retry_count >= max_retries:
                    # ❌ Give up → mark failed
                    update_data["failed_at"] = datetime.utcnow().isoformat()

                outbox_event.update(update_data)
