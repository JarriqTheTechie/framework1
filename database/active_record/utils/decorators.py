def on(event_name: str, priority: int = 0):
    def decorator(fn):
        fn.__event_name__ = event_name
        fn.__event_priority__ = priority
        return fn
    return decorator