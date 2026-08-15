class Base:
    def greet(self):
        return "base"


class Child(Base):
    def greet(self):
        return super().greet() + "!"


def lower(n):
    return n - 1


def shout(s: str) -> str:
    return s.lower()
