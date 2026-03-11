from __future__ import annotations


class KeyringSecretStore:
    def __init__(self, service_name: str) -> None:
        self._service_name = service_name

    def save_secret(self, key: str, value: str) -> str:
        import keyring

        keyring.set_password(self._service_name, key, value)
        return key

    def read_secret(self, key: str) -> str | None:
        import keyring

        return keyring.get_password(self._service_name, key)

    def delete_secret(self, key: str) -> None:
        import keyring

        try:
            keyring.delete_password(self._service_name, key)
        except keyring.errors.PasswordDeleteError:
            return
