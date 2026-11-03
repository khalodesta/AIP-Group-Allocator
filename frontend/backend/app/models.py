from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class Strategy(str, Enum):
    spread = "spread"
    balance = "balance"
    numeric_balance = "numeric_balance"
    numeric_diversity = "numeric_diversity"
    ignore = "ignore"


class Participant(BaseModel):
    id: str
    name: str
    attributes: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class FacultyMember(BaseModel):
    id: str
    name: str
    offering: str


class SupportMember(BaseModel):
    id: str
    name: str


class ChemistryRecord(BaseModel):
    source_name: str
    primary: str
    secondary: str
    participant_id: Optional[str] = None


class Factor(BaseModel):
    id: str
    name: str
    source_column: str
    data_type: str = "categorical"
    strategy: Strategy = Strategy.balance
    weight: int = Field(default=5, ge=0, le=100)
    enabled: bool = True
    missing_handling: str = "exclude"


class Activity(BaseModel):
    id: str
    name: str
    mode: str = "max_size"
    value: int = Field(ge=1, le=60)
    locked: bool = False


class Configuration(BaseModel):
    schema_version: int = 1
    activities: List[Activity]
    factors: List[Factor] = Field(default_factory=list)
    seed: int = 42
    time_limit_seconds: float = Field(default=10, ge=.1, le=120)
    repeat_weight: int = Field(default=1000, ge=1)


class Group(BaseModel):
    id: str
    name: str
    participant_ids: List[str]


class ActivityAllocation(BaseModel):
    activity_id: str
    activity_name: str
    groups: List[Group]
    locked: bool = False


class AllocationSnapshot(BaseModel):
    activities: List[ActivityAllocation]
    status: str = "FEASIBLE"
    objective_value: Optional[float] = None
    seed: int = 42


class OptimizeRequest(BaseModel):
    participants: List[Participant]
    configuration: Configuration
    faculty_members: List[FacultyMember] = Field(default_factory=list)
    support_members: List[SupportMember] = Field(default_factory=list)
    existing_allocation: Optional[AllocationSnapshot] = None
    regenerate_activity_ids: Optional[List[str]] = None
    locked_assignments: Dict[str, Dict[str, str]] = Field(default_factory=dict)


class AllocationRequest(BaseModel):
    participants: List[Participant]
    configuration: Configuration
    allocation: AllocationSnapshot
    faculty_members: List[FacultyMember] = Field(default_factory=list)
    support_members: List[SupportMember] = Field(default_factory=list)


class SwapRequest(AllocationRequest):
    activity_id: str
    participant_a: str
    participant_b: str


class Scenario(BaseModel):
    name: str
    configuration: Configuration


class ScenarioCompareRequest(BaseModel):
    participants: List[Participant]
    scenarios: List[Scenario]
