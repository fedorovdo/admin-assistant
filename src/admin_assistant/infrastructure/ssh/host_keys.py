from __future__ import annotations


class HostKeyStore:
    def load(self) -> None:
        raise NotImplementedError

    def save(self) -> None:
        raise NotImplementedError

