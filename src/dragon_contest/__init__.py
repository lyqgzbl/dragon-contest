from nonebot import get_driver, require
from nonebot.log import logger
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_orm")
require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_apscheduler")

from .commands.command_registry import (
    plugin_config,
    dragon_contest_command,
    join_dragon_contest_command,
    cancel_dragon_contest_command,
    revise_dragon_name_command,
)


__plugin_meta__ = PluginMetadata(
    name="dragon-contest",
    description="龙龙大赛插件",
    usage="/加入龙龙大赛 <龙龙名称>",
    type="application",
    homepage="https://github.com/lyqgzbl/dragon-contest",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "author": "lyqgzbl <admin@lyqgzbl.com>",
        "version": "1.4.0",
    },
)


api_key = plugin_config.dc_api_key or plugin_config.dc_github_token
base_url = plugin_config.dc_base_url
if not base_url and plugin_config.dc_github_token and not plugin_config.dc_api_key:
    base_url = "https://models.github.ai/inference"

if not api_key:
    logger.opt(colors=True).warning(
        "<yellow>缺失必要配置项 'dc_api_key' 或 'dc_github_token'，"
        "已禁用龙龙大赛插件</yellow>"
    )
    openai_handler = None
else:
    from .openai_client import OpenAIHandler

    openai_handler = OpenAIHandler(
        api_key=api_key,
        base_url=base_url,
        model_name=plugin_config.dc_ai_model_name,
        temperature=0.7,
        top_p=0.9,
    )
    handler = openai_handler

    @get_driver().on_shutdown
    async def _close_openai_handler():
        await handler.close()


from .commands import admin as _admin  # noqa: F401
from .commands import signup as _signup  # noqa: F401


__all__ = [
    "cancel_dragon_contest_command",
    "dragon_contest_command",
    "join_dragon_contest_command",
    "openai_handler",
    "revise_dragon_name_command",
]
