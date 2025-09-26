# lib/domain/saga.py
from typing import Callable

class SagaStep:
    def __init__(self, action: Callable, compensate: Callable | None = None):
        self.action = action
        self.compensate = compensate

class Saga:
    def __init__(self, steps: list[SagaStep]):
        self.steps = steps
        self.completed_steps = []

    def execute(self):
        try:
            for step in self.steps:
                step.action()
                self.completed_steps.append(step)
        except Exception as e:
            self.rollback()
            raise e

    def rollback(self):
        for step in reversed(self.completed_steps):
            if step.compensate:
                try:
                    step.compensate()
                except Exception as e:
                    print(f"[Saga] Compensation failed: {e}")
