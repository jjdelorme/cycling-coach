# Cycling Coach Platform

## Overview

A web-based cycling coaching platform for a single athlete (50yo male, targeting Big Sky Biggie in late August 2026). It ingests ride data from Garmin/TrainingPeaks, computes training metrics, and provides AI-powered coaching insights via an LLM abstraction layer.

Raw training data (FIT files, ride JSON, planned workouts) lives in GCS at `gs://jasondel-coach-data`. The app ingests from there into PostgreSQL. The build plan is at `plans/coaching-platform-build-plan.md`.

## Glossary

| Term | Full Name | Description |
|------|-----------|-------------|
| **PMC** | Performance Management Chart | Plot of CTL, ATL, and TSB over time; the core training analytics model |
| **CTL** | Chronic Training Load | Rolling ~42-day weighted average of daily TSS; represents "fitness" |
| **ATL** | Acute Training Load | Rolling ~7-day weighted average of daily TSS; represents "fatigue" |
| **TSB** | Training Stress Balance | CTL minus ATL; represents "form" (positive = fresh, negative = fatigued) |
| **TSS** | Training Stress Score | Normalized measure of training load for a single ride, relative to FTP |
| **FTP** | Functional Threshold Power | Maximum sustainable power for ~1 hour (watts); primary fitness benchmark |
| **NP** | Normalized Power | Weighted average power that accounts for variability in effort |
| **IF** | Intensity Factor | Ratio of NP to FTP; 1.0 = threshold effort |
| **EF** | Efficiency Factor | NP divided by average HR; rising EF = improving aerobic fitness |
| **W/kg** | Watts per Kilogram | Power-to-weight ratio; critical metric for climbing performance |
| **FIT** | Flexible and Interoperable Data Transfer | Garmin's binary file format for recording ride data |
| **ZWO** | Zwift Workout | XML file format defining structured workout intervals |
| **Z0-Z5** | Power Zones 0-5 | Training intensity zones based on percentage of FTP (Z0=recovery through Z5=VO2max+) |
| **ADC** | Application Default Credentials | GCP authentication method; no API keys needed |
