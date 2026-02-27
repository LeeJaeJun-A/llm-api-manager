"""
Custom LiteLLM callback that maps team_id (customer ID) to Langfuse trace userId.

Every LLM call through the proxy automatically gets tagged with the customer's
team_id as the Langfuse userId, enabling per-customer trace filtering and
cost aggregation in Langfuse's User views.
"""

from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy.proxy_server import UserAPIKeyAuth, DualCache
from typing import Literal


class TeamIdToLangfuseUser(CustomLogger):

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
        ],
    ):
        metadata = data.get("metadata") or {}

        team_id = getattr(user_api_key_dict, "team_id", None)
        if team_id and "trace_user_id" not in metadata:
            metadata["trace_user_id"] = team_id

        if "trace_name" not in metadata:
            model = data.get("model") or ""
            metadata["trace_name"] = model

        data["metadata"] = metadata
        return data


proxy_handler_instance = TeamIdToLangfuseUser()
