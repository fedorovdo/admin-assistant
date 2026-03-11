from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
)


class IncidentDialog(QDialog):
    def __init__(self, target_count: int, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Investigate Incident")

        layout = QFormLayout(self)
        self.target_label = QLabel(f"Running on {target_count} selected target(s).", self)
        self.title_input = QLineEdit(self)
        self.title_input.setPlaceholderText("Optional short incident title")
        self.symptom_input = QTextEdit(self)
        self.symptom_input.setPlaceholderText(
            "Describe the symptom, for example: Users cannot SSH to web-01 and CPU is high."
        )
        self.symptom_input.setMinimumHeight(120)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )

        layout.addRow("Targets", self.target_label)
        layout.addRow("Title", self.title_input)
        layout.addRow("Symptom", self.symptom_input)
        layout.addRow(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def incident_title(self) -> str:
        return self.title_input.text().strip()

    def incident_symptom(self) -> str:
        return self.symptom_input.toPlainText().strip()
