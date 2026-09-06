from pydantic import BaseModel, Field

from app.contracts.common import now_iso


class MiroFishLaunch(BaseModel):
    attempted: bool = False
    ok: bool = False
    project_id: str | None = None
    error: str | None = None
    mirofish_url: str | None = None
    at: str | None = None


class MiroFishPack(BaseModel):
    """Handoff from this engine to MiroFish: a population seed + sim prompt."""

    seed_filename: str = "mirofish_seed.md"
    seed_markdown: str
    simulation_requirement: str
    population_size: int = 0
    agent_count: int = 0
    launch: MiroFishLaunch = Field(default_factory=MiroFishLaunch)
    built_at: str = Field(default_factory=now_iso)
