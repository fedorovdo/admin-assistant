from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from pydantic import SecretStr

from admin_assistant.modules.settings.dto import (
    AIProviderConfigCreateRequest,
    AIProviderConfigUpdateRequest,
    AIProviderConfigView,
    ProviderConnectionTestRequest,
)
from admin_assistant.modules.settings.service import SettingsService


class ProviderDialog(QDialog):
    def __init__(self, settings_service: SettingsService, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self._settings_service = settings_service
        self.setWindowTitle("Configure AI Provider")
        self._provider_config_id: str | None = None
        self._loading_provider = False

        layout = QFormLayout(self)
        self.display_name_input = QLineEdit(self)
        self.provider_type_combo = QComboBox(self)
        self.provider_type_combo.addItem("OpenAI", "openai")
        self.provider_type_combo.addItem("Ollama", "ollama")
        self.provider_type_combo.addItem("OpenAI-Compatible", "openai_compatible")
        self.base_url_input = QLineEdit(self)
        self.model_name_input = QLineEdit(self)
        self.api_key_label = QLabel("API Key", self)
        self.api_key_input = QLineEdit(self)
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.timeout_input = QSpinBox(self)
        self.timeout_input.setRange(1, 300)
        self.timeout_input.setValue(30)
        self.test_button = QPushButton("Test Connection", self)
        self.status_label = QLabel("Use Test Connection to verify this provider before saving.", self)
        self.status_label.setWordWrap(True)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.status_label, 1)

        layout.addRow("Display Name", self.display_name_input)
        layout.addRow("Provider", self.provider_type_combo)
        layout.addRow("Base URL", self.base_url_input)
        layout.addRow("Model", self.model_name_input)
        layout.addRow(self.api_key_label, self.api_key_input)
        layout.addRow("Timeout", self.timeout_input)
        layout.addRow(test_row)
        layout.addRow(self.button_box)

        self.provider_type_combo.currentIndexChanged.connect(self._apply_provider_defaults)
        self.test_button.clicked.connect(self._test_connection)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self._apply_provider_defaults()

    def to_create_request(self) -> AIProviderConfigCreateRequest:
        provider_name = self._selected_provider_name()
        api_key = self.api_key_input.text().strip()
        return AIProviderConfigCreateRequest(
            provider_name=provider_name,
            display_name=self.display_name_input.text().strip() or self._default_display_name(provider_name),
            base_url=self.base_url_input.text().strip() or self._default_base_url(provider_name),
            model_name=self.model_name_input.text().strip() or self._default_model(provider_name),
            api_key=SecretStr(api_key) if self._provider_requires_api_key(provider_name) and api_key else None,
            timeout_sec=self.timeout_input.value(),
            is_default=True,
            is_enabled=True,
        )

    def to_update_request(self) -> AIProviderConfigUpdateRequest:
        if self._provider_config_id is None:
            raise ValueError("Provider config has not been loaded for update.")
        provider_name = self._selected_provider_name()
        api_key = self.api_key_input.text().strip()
        return AIProviderConfigUpdateRequest(
            provider_config_id=self._provider_config_id,
            provider_name=provider_name,
            display_name=self.display_name_input.text().strip() or self._default_display_name(provider_name),
            base_url=self.base_url_input.text().strip() or self._default_base_url(provider_name),
            model_name=self.model_name_input.text().strip() or self._default_model(provider_name),
            api_key=SecretStr(api_key) if self._provider_requires_api_key(provider_name) and api_key else None,
            timeout_sec=self.timeout_input.value(),
            is_default=True,
            is_enabled=True,
        )

    def load_provider(self, provider: AIProviderConfigView) -> None:
        self._loading_provider = True
        self._provider_config_id = provider.id
        index = self.provider_type_combo.findData(provider.provider_name)
        self.provider_type_combo.setCurrentIndex(index if index >= 0 else 0)
        self.display_name_input.setText(provider.display_name)
        self.base_url_input.setText(provider.base_url)
        self.model_name_input.setText(provider.model_name)
        self.timeout_input.setValue(provider.timeout_sec)
        self.api_key_input.clear()
        if self._provider_requires_api_key(provider.provider_name):
            self.api_key_input.setPlaceholderText("Leave blank to keep existing API key")
        else:
            self.api_key_input.setPlaceholderText("No API key required for this provider")
        self._update_api_key_visibility(provider.provider_name)
        self._loading_provider = False

    def _apply_provider_defaults(self, _index: int | None = None) -> None:
        provider_name = self._selected_provider_name()
        self._update_api_key_visibility(provider_name)
        if self._loading_provider:
            return

        self.display_name_input.setText(self._default_display_name(provider_name))
        self.base_url_input.setText(self._default_base_url(provider_name))
        self.model_name_input.setText(self._default_model(provider_name))
        self.timeout_input.setValue(self._default_timeout(provider_name))
        self.api_key_input.clear()
        if self._provider_requires_api_key(provider_name):
            self.api_key_input.setPlaceholderText("")
        else:
            self.api_key_input.setPlaceholderText("No API key required for this provider")
        self.status_label.setText("Use Test Connection to verify this provider before saving.")

    def _update_api_key_visibility(self, provider_name: str) -> None:
        visible = self._provider_requires_api_key(provider_name)
        self.api_key_label.setVisible(visible)
        self.api_key_input.setVisible(visible)

    def _selected_provider_name(self) -> str:
        provider_name = self.provider_type_combo.currentData()
        return provider_name if isinstance(provider_name, str) else "openai"

    def _provider_requires_api_key(self, provider_name: str) -> bool:
        return provider_name in {"openai", "openai_compatible"}

    def _default_display_name(self, provider_name: str) -> str:
        return {
            "openai": "OpenAI",
            "ollama": "Ollama",
            "openai_compatible": "OpenAI-Compatible",
        }.get(provider_name, "AI Provider")

    def _default_base_url(self, provider_name: str) -> str:
        return {
            "openai": "https://api.openai.com/v1",
            "ollama": "http://localhost:11434",
            "openai_compatible": "https://api.openai.com/v1",
        }.get(provider_name, "")

    def _default_model(self, provider_name: str) -> str:
        return {
            "openai": "gpt-4o-mini",
            "ollama": "llama3",
            "openai_compatible": "gpt-4o-mini",
        }.get(provider_name, "")

    def _default_timeout(self, provider_name: str) -> int:
        return {
            "openai": 30,
            "ollama": 180,
            "openai_compatible": 30,
        }.get(provider_name, 30)

    def _test_connection(self) -> None:
        try:
            result = self._settings_service.test_provider_connection(self.to_test_request())
        except Exception as exc:  # pragma: no cover - UI display path
            self.status_label.setText(str(exc))
            return
        self.status_label.setText(result.message)

    def to_test_request(self) -> ProviderConnectionTestRequest:
        provider_name = self._selected_provider_name()
        api_key = self.api_key_input.text().strip()
        return ProviderConnectionTestRequest(
            provider_config_id=self._provider_config_id,
            provider_name=provider_name,
            base_url=self.base_url_input.text().strip() or self._default_base_url(provider_name),
            model_name=self.model_name_input.text().strip() or self._default_model(provider_name),
            api_key=SecretStr(api_key) if self._provider_requires_api_key(provider_name) and api_key else None,
            timeout_sec=self.timeout_input.value(),
        )
