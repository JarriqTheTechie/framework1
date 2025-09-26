# -------------------------------------------------------------------
# Domain Event Subscription Central Registry
# -------------------------------------------------------------------
# Example usage:
#
# @dataclass(frozen=True)
# class PaymentReceived:
#     payment_id: int
#     client_id: int
#     amount: float
#     occurred_at: datetime = datetime.utcnow()
#
# def trigger_risk_scoring(event: PaymentReceived):
#     print(f"[AML] Risk scoring for Client {event.client_id} on Payment {event.payment_id} (${event.amount})")
#
#
# DomainEventBus.subscribe(PaymentReceived, trigger_risk_scoring)
# -------------------------------------------------------------------

