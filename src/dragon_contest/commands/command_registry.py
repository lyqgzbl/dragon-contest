from nonebot import get_plugin_config
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule
from arclet.alconna import Args, Alconna, CommandMeta, Option, Subcommand
from nonebot_plugin_alconna import on_alconna

from ..config import Config


plugin_config = get_plugin_config(Config)


def is_enable() -> Rule:
    def _rule() -> bool:
        return bool(plugin_config.dc_github_token)
    return Rule(_rule)


dragon_contest_command = on_alconna(
    Alconna(
        "dragon_contest",
        Subcommand(
            "create|创建",
            Args["date#比赛日期(YYYY/MM/DD)", str],
            Args["time#比赛时间(HH:MM)", str],
            Option(
                "-n|number",
                Args["limit#参加人数限制,最大值为 32", int],
            ),
            help_text="创建一个新的龙龙大赛,时间格式为 YYYY/MM/DD HH:MM",
        ),
        Subcommand(
            "delete|删除",
            Args["id#比赛ID", int],
            help_text="删除指定ID的龙龙大赛",
        ),
        Subcommand(
            "force_delete|强制删除",
            Args["id#比赛ID", int],
            help_text="强制删除指定ID的龙龙大赛（即使正在进行中）",
        ),
        Subcommand(
            "list|列表",
            help_text="列出所有正在进行的龙龙大赛",
        ),
        Subcommand(
            "status|状态",
            help_text="显示龙龙大赛报名状态",
        ),
        meta=CommandMeta(
            compact=True,
            description="龙龙大赛管理系统",
            usage="使用样例: /龙龙大赛 创建 2025/08/05 22:00",
            example="/龙龙大赛 创建 2025/08/05 22:00",
        ),
    ),
    permission=SUPERUSER,
    aliases={"龙龙大赛"},
    use_cmd_start=True,
    rule=is_enable(),
    priority=10,
    block=True,
)


add_dragon_contest_player_command = on_alconna(
    Alconna(
        "添加龙龙大赛参赛者",
        Args["user_id#用户ID", str],
        Args["name#龙龙名称", str],
        meta=CommandMeta(
            compact=True,
            description="为当前龙龙大赛添加参赛者",
            usage="/添加龙龙大赛参赛者 用户ID 龙龙名称",
            example="/添加龙龙大赛参赛者 12345678 我的龙龙",
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
    priority=10,
    block=True,
)


remove_dragon_contest_player_command = on_alconna(
    Alconna(
        "移除龙龙大赛参赛者",
        Args["user_id#用户ID", str],
        meta=CommandMeta(
            compact=True,
            description="移除当前龙龙大赛的参赛者",
            usage="/移除龙龙大赛参赛者 用户ID",
            example="/移除龙龙大赛参赛者 12345678",
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
    priority=10,
    block=True,
)


list_dragon_contest_player_command = on_alconna(
    Alconna(
        "龙龙大赛参赛名单",
        meta=CommandMeta(
            compact=True,
            description="查看当前龙龙大赛的参赛名单",
            usage="/龙龙大赛参赛名单",
            example="/龙龙大赛参赛名单",
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
    priority=10,
    block=True,
)


join_dragon_contest_command = on_alconna(
    Alconna(
        "加入龙龙大赛",
        Args["name#龙龙名称", str],
        meta=CommandMeta(
            compact=True,
            description="加入龙龙大赛",
            usage="/加入龙龙大赛",
            example="/加入龙龙大赛 玉涛性欲姬",
        ),
    ),
    use_cmd_start=True,
    priority=10,
    block=True,
)


cancel_dragon_contest_command = on_alconna(
    Alconna(
        "取消报名",
        meta=CommandMeta(
            compact=True,
            description="取消已报名的龙龙大赛",
            usage="/取消报名",
            example="/取消报名",
        ),
    ),
    use_cmd_start=True,
    priority=10,
    block=True,
)


revise_dragon_name_command = on_alconna(
    Alconna(
        "修改龙龙名称",
        Args["name#新的龙龙名称", str],
        meta=CommandMeta(
            compact=True,
            description="修改已报名的龙龙大赛",
            usage="/修改龙龙名称",
            example="/修改龙龙名称 新的龙龙名称",
        ),
    ),
    use_cmd_start=True,
    priority=10,
    block=True,
)


dragon_name_comparison_command = on_alconna(
    Alconna(
        "龙龙名称比较",
        Args["name1#龙龙名称1", str],
        Args["name2#龙龙名称2", str],
        meta=CommandMeta(
            compact=True,
            description="对比两个龙龙名称",
            usage="/龙龙名称比较 龙龙名称1 龙龙名称2",
            example="/龙龙名称比较 玉涛性欲姬 一条咸鱼剑",
        ),
    ),
    use_cmd_start=True,
    priority=10,
    block=True,
)


__all__ = [
    "plugin_config",
    "is_enable",
    "dragon_contest_command",
    "add_dragon_contest_player_command",
    "remove_dragon_contest_player_command",
    "list_dragon_contest_player_command",
    "join_dragon_contest_command",
    "cancel_dragon_contest_command",
    "revise_dragon_name_command",
    "dragon_name_comparison_command",
]
