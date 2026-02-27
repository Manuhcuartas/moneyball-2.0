from enum import Enum, auto
from typing import Optional, List, NewType
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4

# --- STRONG TYPING ---
PlayerID = NewType("PlayerID", UUID)
TeamID = NewType("TeamID", UUID)
MatchID = NewType("MatchID", UUID)

# --- ENUMS ---
class ShotType(str, Enum):
    TWO_POINT = "2PT"
    THREE_POINT = "3PT"
    FREE_THROW = "FT"

class ShotOutcome(str, Enum):
    MADE = "MADE"
    MISSED = "MISSED"
    BLOCKED = "BLOCKED"

class Zone(str, Enum):
    # Zones for shot charts
    PAINT = "PAINT"          
    MID_RANGE = "MID_RANGE"  
    CORNER_3 = "CORNER_3"    
    ABOVE_BREAK_3 = "ABOVE_3"
    BACKCOURT = "BACKCOURT"  

class PossessionEndType(str, Enum):
    MADE_SHOT = "MADE_SHOT"
    DEFENSIVE_REBOUND = "DEF_REBOUND"
    TURNOVER = "TURNOVER"
    END_OF_QUARTER = "EOQ"

# --- VALUE OBJECTS ---
class CourtLocation(BaseModel):
    x: float = Field(..., ge=0) # Normalized 0-100% width
    y: float = Field(..., ge=0) # Normalized 0-100% height
    
    def determine_zone(self) -> Zone:
        # TODO: Implement logic to determine zone based on x and y coordinates
        return Zone.PAINT 

class GameClock(BaseModel):
    period: int
    minutes: int
    seconds: float
    total_seconds_remaining: float


class DomainEvent(BaseModel):
    """Game atomic event, e.g: shot attempt, rebound, assist, etc."""
    id: UUID = Field(default_factory=uuid4)
    match_id: MatchID
    team_id: Optional[TeamID] # Puede ser None (e.g: EOQ)
    player_id: Optional[PlayerID]
    
    clock: GameClock
    location: Optional[CourtLocation] = None
    
    event_type: str # "SHOT", "REBOUND", etc.
    metadata: dict = {} # extra date (e.g: assist)

class Possession(BaseModel):
    """
        A possesion groups all events from the moment a team gains control of the ball until they lose it.
        Pace = (Possesions Team A + Possesions Team B) / Minutos
    """
    id: UUID = Field(default_factory=uuid4)
    team_id: TeamID
    match_id: MatchID
    
    start_clock: GameClock
    end_clock: GameClock
    duration_seconds: float
    
    points_scored: int = 0
    end_type: PossessionEndType
    
    events: List[DomainEvent] = []

    @property
    def is_efficient(self) -> bool:
        return self.points_scored > 0

class Player(BaseModel):
    id: PlayerID
    name: str
    number: str
    # External ID Mapping
    external_refs: dict[str, str] = {} 

class Team(BaseModel):
    id: TeamID
    name: str
    external_refs: dict[str, str] = {}

class Match(BaseModel):
    id: MatchID
    date: datetime
    home_team: Team
    away_team: Team
    
    # State of the game
    home_score: int = 0
    away_score: int = 0
    
    events: List[DomainEvent] = []
    possessions: List[Possession] = [] # calculated from events, but stored here for easy access
    
    def calculate_advanced_stats(self):
        """
        Pure business logic method to calculate advanced stats like Pace, Offensive Rating, etc. based on self.possessions
        """
        #TODO: Implement advanced stats calculations
        pass
    
    def add_event(self, event: DomainEvent):
        self.events.append(event)
        # TODO: Logic for detecting possession changes and updating self.possessions accordingly