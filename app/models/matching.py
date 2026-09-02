from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class MatchScoreBreakdown(BaseModel):
    skill_match_points: float = Field(..., description="50.0 points if skill matches, 0.0 otherwise")
    distance_points: float = Field(..., description="max(0, 20 - distance_km) points")
    rating_points: float = Field(..., description="worker rating * 5.0 points")
    active_bookings_penalty: float = Field(..., description="-(active_bookings * 3.0) points penalty")
    total_score: float = Field(..., description="Calculated overall score")

class MatchedWorker(BaseModel):
    worker_id: str
    user_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    skill: str
    cooperative_id: Optional[str] = None
    cooperative_name: Optional[str] = None
    rating: float
    verified_status: bool
    availability: bool
    distance_km: float
    current_active_bookings: int
    score: float
    breakdown: MatchScoreBreakdown

    model_config = ConfigDict(from_attributes=True)

class MatchResponse(BaseModel):
    booking_id: str
    requested_skill: str
    household_location: Dict[str, float]
    total_candidates_evaluated: int
    ranked_workers: List[MatchedWorker]
