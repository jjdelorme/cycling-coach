"""Pydantic models for API request/response schemas."""

from datetime import date, datetime
from pydantic import BaseModel
from typing import Optional, Union


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
    start_time: Optional[Union[str, datetime]] = None


class RideRecord(BaseModel):
    timestamp_utc: Optional[Union[str, datetime]] = None
    power: Optional[int] = None
    heart_rate: Optional[int] = None
    cadence: Optional[int] = None
    speed: Optional[float] = None
    altitude: Optional[float] = None
    distance: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    temperature: Optional[float] = None


class RideLap(BaseModel):
    lap_index: int
    start_time: Optional[str] = None
    total_timer_time: Optional[float] = None
    total_elapsed_time: Optional[float] = None
    total_distance: Optional[float] = None
    avg_power: Optional[int] = None
    normalized_power: Optional[int] = None
    max_power: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_cadence: Optional[int] = None
    max_cadence: Optional[int] = None
    avg_speed: Optional[float] = None
    max_speed: Optional[float] = None
    total_ascent: Optional[int] = None
    total_descent: Optional[int] = None
    total_calories: Optional[int] = None
    total_work: Optional[int] = None
    intensity: Optional[str] = None
    lap_trigger: Optional[str] = None
    wkt_step_index: Optional[int] = None
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None
    avg_temperature: Optional[float] = None


class RideDetail(RideSummary):
    records: list[RideRecord] = []
    laps: list[RideLap] = []


class PMCEntry(BaseModel):
    date: Union[str, date]
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


class DailySummary(BaseModel):
    date: str
    rides: int = 0
    duration_s: float = 0
    tss: float = 0
    total_calories: int = 0
    distance_m: float = 0
    ascent_m: int = 0
    avg_power: Optional[int] = None


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
    avg_hr: Optional[float] = None
    date: Union[str, date]
    ride_id: int


class PlannedWorkout(BaseModel):
    id: int
    date: Optional[Union[str, date]] = None
    name: Optional[str] = None
    sport: Optional[str] = None
    total_duration_s: Optional[float] = None
    planned_tss: Optional[float] = None
    workout_xml: Optional[str] = None
    coach_notes: Optional[str] = None
    athlete_notes: Optional[str] = None


class PeriodizationPhase(BaseModel):
    id: int
    name: str
    start_date: Union[str, date]
    end_date: Union[str, date]
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


# --- Nutrition Schemas ---

class MealItem(BaseModel):
    id: Optional[int] = None
    name: str
    serving_size: Optional[str] = None
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float


class MealSummary(BaseModel):
    id: int
    date: str
    logged_at: str
    meal_type: Optional[str] = None
    description: str
    total_calories: int
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    confidence: str
    photo_url: Optional[str] = None
    edited_by_user: bool = False
    user_notes: Optional[str] = None
    agent_notes: Optional[str] = None


class MealDetail(MealSummary):
    items: list[MealItem] = []


class MacroTargets(BaseModel):
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    updated_at: Optional[str] = None


class DailyNutritionSummary(BaseModel):
    date: str
    total_calories_in: int
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    meal_count: int
    target_calories: int
    target_protein_g: float
    target_carbs_g: float
    target_fat_g: float
    remaining_calories: int
    calories_out: dict
    net_caloric_balance: int


class MealUpdateRequest(BaseModel):
    total_calories: Optional[int] = None
    total_protein_g: Optional[float] = None
    total_carbs_g: Optional[float] = None
    total_fat_g: Optional[float] = None
    meal_type: Optional[str] = None
    date: Optional[str] = None
    logged_at: Optional[str] = None
    items: Optional[list[MealItem]] = None
    user_notes: Optional[str] = None


class PlannedMeal(BaseModel):
    id: int
    user_id: str = "athlete"
    date: str
    meal_slot: str
    name: str
    description: Optional[str] = None
    total_calories: int
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    items: Optional[list[MealItem]] = None
    agent_notes: Optional[str] = None
    created_at: Optional[str] = None


class MealPlanDayTotals(BaseModel):
    planned_calories: int = 0
    actual_calories: int = 0
    planned_protein_g: float = 0
    actual_protein_g: float = 0
    planned_carbs_g: float = 0
    actual_carbs_g: float = 0
    planned_fat_g: float = 0
    actual_fat_g: float = 0


class MealPlanDay(BaseModel):
    date: str
    planned: dict[str, Optional[PlannedMeal]] = {}
    actual: list[MealSummary] = []
    day_totals: MealPlanDayTotals = MealPlanDayTotals()


class DietaryPreferencesUpdate(BaseModel):
    section: str  # "dietary_preferences" or "nutritionist_principles"
    value: str


class NutritionChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    image_data: Optional[str] = None
    image_mime_type: Optional[str] = None


class NutritionChatResponse(BaseModel):
    response: str
    session_id: str
    requires_clarification: bool = False
    meal_saved: bool = False
