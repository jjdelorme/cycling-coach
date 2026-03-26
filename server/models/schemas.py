"""Pydantic models for API request/response schemas."""

from pydantic import BaseModel
from typing import Optional


class RideSummary(BaseModel):
    id: int
    date: str
    filename: str
    sport: Optional[str] = None
    sub_sport: Optional[str] = None
    duration_s: Optional[float] = None
    distance_m: Optional[float] = None
    avg_power: Optional[int] = None
    normalized_power: Optional[int] = None
    max_power: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_cadence: Optional[int] = None
    total_ascent: Optional[int] = None
    total_descent: Optional[int] = None
    total_calories: Optional[int] = None
    tss: Optional[float] = None
    intensity_factor: Optional[float] = None
    ftp: Optional[int] = None
    total_work_kj: Optional[float] = None
    training_effect: Optional[float] = None
    variability_index: Optional[float] = None
    best_1min_power: Optional[int] = None
    best_5min_power: Optional[int] = None
    best_20min_power: Optional[int] = None
    best_60min_power: Optional[int] = None
    weight: Optional[float] = None
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    post_ride_comments: Optional[str] = None
    coach_comments: Optional[str] = None
    title: Optional[str] = None


class RideRecord(BaseModel):
    timestamp_utc: Optional[str] = None
    power: Optional[int] = None
    heart_rate: Optional[int] = None
    cadence: Optional[int] = None
    speed: Optional[float] = None
    altitude: Optional[float] = None
    distance: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    temperature: Optional[float] = None


class RideDetail(RideSummary):
    records: list[RideRecord] = []


class PMCEntry(BaseModel):
    date: str
    total_tss: Optional[float] = None
    ctl: Optional[float] = None
    atl: Optional[float] = None
    tsb: Optional[float] = None
    weight: Optional[float] = None


class WeeklySummary(BaseModel):
    week: str
    rides: int = 0
    duration_h: float = 0
    tss: float = 0
    distance_km: float = 0
    ascent_m: int = 0
    avg_power: Optional[float] = None
    avg_hr: Optional[float] = None
    best_20min: Optional[int] = None


class MonthlySummary(BaseModel):
    month: str
    rides: int = 0
    duration_h: float = 0
    tss: float = 0
    distance_km: float = 0
    ascent_m: int = 0
    avg_power: Optional[float] = None
    avg_hr: Optional[float] = None
    best_20min: Optional[int] = None


class PowerBestEntry(BaseModel):
    duration_s: int
    power: float
    date: str
    ride_id: int


class PlannedWorkout(BaseModel):
    id: int
    date: Optional[str] = None
    name: Optional[str] = None
    sport: Optional[str] = None
    total_duration_s: Optional[float] = None
    workout_xml: Optional[str] = None
    coach_notes: Optional[str] = None
    athlete_notes: Optional[str] = None


class PeriodizationPhase(BaseModel):
    id: int
    name: str
    start_date: str
    end_date: str
    focus: Optional[str] = None
    hours_per_week_low: Optional[float] = None
    hours_per_week_high: Optional[float] = None
    tss_target_low: Optional[float] = None
    tss_target_high: Optional[float] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class SessionSummary(BaseModel):
    session_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str


class SessionMessage(BaseModel):
    author: Optional[str] = None
    role: Optional[str] = None
    content_text: Optional[str] = None
    timestamp: str


class SessionDetail(BaseModel):
    session_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    messages: list[SessionMessage] = []
