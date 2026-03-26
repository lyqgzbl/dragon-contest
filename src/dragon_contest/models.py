from enum import Enum
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, UniqueConstraint, String, JSON


class DragonContestConfig(Model):
    __tablename__ = "dragon_contest_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    default_limit: Mapped[int] = mapped_column(nullable=False)


class ContestStatus(str, Enum):
    SIGNUP = "signup"
    RUNNING = "running"
    FINISHED = "finished"


class DragonContest(Model):
    __tablename__ = "dragon_contest"
    id: Mapped[int] = mapped_column(primary_key=True)
    start_ts: Mapped[int] = mapped_column(index=True)
    limit: Mapped[int] = mapped_column(nullable=False)
    target: Mapped[dict] = mapped_column(JSON, nullable=False)
    current_round: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(
        String(16),
        default=ContestStatus.SIGNUP.value,
        nullable=False,
        index=True,
    )


class DragonContestPlayer(Model):
    __tablename__ = "dragon_contest_player"
    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("dragon_contest.id"),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(index=True)
    dragon_name: Mapped[str] = mapped_column(String(32))
    eliminated: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("contest_id", "user_id"),)
