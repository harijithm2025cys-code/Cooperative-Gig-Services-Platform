from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class RatingCreate(BaseModel):
    booking_id: str = Field(..., description="Completed booking ID")
    rating: int = Field(..., ge=1, le=5, description="Rating score from 1 to 5 stars")
    review_text: Optional[str] = Field(None, max_length=1000, description="Optional text review")

    model_config = ConfigDict(from_attributes=True)

class RatingResponse(BaseModel):
    id: str
    booking_id: str
    rating: int
    review_text: Optional[str] = None
    created_at: Optional[datetime] = None
    household_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class WorkerRatingsSummaryResponse(BaseModel):
    worker_id: str
    average_rating: float
    total_reviews: int
    reviews: List[RatingResponse]
