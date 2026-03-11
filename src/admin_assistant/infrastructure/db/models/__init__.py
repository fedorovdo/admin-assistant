"""SQLAlchemy ORM record definitions."""

from admin_assistant.infrastructure.db.models.ai_analysis_record import AIAnalysisRecord
from admin_assistant.infrastructure.db.models.ai_provider_config_record import AIProviderConfigRecord
from admin_assistant.infrastructure.db.models.ai_suggested_action_record import AISuggestedActionRecord
from admin_assistant.infrastructure.db.models.app_setting_record import AppSettingRecord
from admin_assistant.infrastructure.db.models.run_output_chunk_record import RunOutputChunkRecord
from admin_assistant.infrastructure.db.models.run_target_result_record import RunTargetResultRecord
from admin_assistant.infrastructure.db.models.script_record import ScriptRecord
from admin_assistant.infrastructure.db.models.script_run_record import ScriptRunRecord
from admin_assistant.infrastructure.db.models.server_record import ServerRecord

__all__ = [
    "AIAnalysisRecord",
    "AIProviderConfigRecord",
    "AISuggestedActionRecord",
    "AppSettingRecord",
    "RunOutputChunkRecord",
    "RunTargetResultRecord",
    "ScriptRecord",
    "ScriptRunRecord",
    "ServerRecord",
]
