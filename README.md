# Cycling Coaching Platform

A powerful, AI-integrated coaching platform for cyclists. This application ingests ride data, computes advanced training metrics (PMC), and provides personalized coaching insights using Gemini.

![Dashboard](docs/images/dashboard.png)

![Rides](docs/images/rides.png)

## Features

- **Performance Management Chart (PMC)**: Track your Fitness (CTL), Fatigue (ATL), and Form (TSB) over time.
- **Ride Analysis**: Detailed breakdown of every ride, including power, heart rate, and interval data.
- **AI Coaching**: An integrated AI coach that analyzes your training history to provide insights, recommendations, and structured workouts.
- **Structured Workouts**: Generate and sync workouts directly to Intervals.icu and Garmin.
- **Automated Sync**: Seamlessly pull data from Intervals.icu.

## How it Works

The platform acts as an intelligent layer on top of your existing cycling data ecosystem. It pulls raw activity data and wellness metrics, processes them to calculate training stress, and uses an LLM-based agent to provide a conversational coaching experience.

### Technical Stack
- **Backend**: FastAPI (Python)
- **Frontend**: React + TypeScript + Tailwind CSS
- **Database**: PostgreSQL
- **AI**: Gemini (via Vertex AI)
  - Google Agent Development Kit (ADK)
- **Integrations**: Intervals.icu API

## Systems of Record

To ensure data consistency across your devices and platforms, the following data flow is recommended:

### Weight (Wellness)
**Garmin Connect** is the primary system of record for weight. 
1. Update your weight in Garmin Connect (or via a Garmin-compatible scale).
2. **Intervals.icu** automatically pulls this weight data from Garmin.
3. The **Coaching Platform** pulls the latest weight from Intervals.icu during sync.

### FTP (Functional Threshold Power)
**Intervals.icu** is the primary system of record for FTP and training zones.
1. When the AI Coach recommends an FTP update or you perform a test, update it in **Intervals.icu**.
2. The **Coaching Platform** uses this FTP to calculate Intensity Factor (IF) and TSS for future workouts.
3. **Manual Sync**: You must manually update your FTP in **Garmin Connect** settings to ensure your bike computer's on-screen zones and recovery metrics are accurate.

### Data Flow Diagram

```mermaid
sequenceDiagram
    participant G as Garmin Connect
    participant I as Intervals.icu
    participant A as AI Coaching App
    
    Note over G,A: Weight Sync
    G->>I: Pulls weight (Wellness sync)
    I->>A: Pulls weight (API)
    
    Note over G,A: FTP & Workout Sync
    A->>I: Push planned workouts (Absolute Watts)
    I->>G: Syncs calendar (Absolute Watts)
    Note right of G: Targets are correct even if<br/>Garmin FTP is outdated.
    
    Note over G,A: Manual Steps
    A-->>I: User updates FTP in Intervals
    I-->>G: User manually updates FTP in Garmin
```

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js & npm
- PostgreSQL (or Podman/Docker)
- Intervals.icu API Key & Athlete ID

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/jasondel/coach.git
   cd coach
   ```

2. **Backend Setup**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env  # Update with your credentials
   ```

3. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   npm run build
   ```

4. **Run the App**:
   ```bash
   # From the root
   ./scripts/dev.sh
   ```

## Development

- **Backend**: `uvicorn server.main:app --reload`
- **Frontend**: `cd frontend && npm run dev`
- **Testing**: `pytest`

## Releases

Releases are managed via the `/release` skill in Claude Code. Production deploys to Cloud Run automatically when a tag is pushed (Cloud Build trigger).

### Version scheme

`major.minor.patch` — semantic versioning:

| Command | Bumps | Tag | Use when |
|---|---|---|---|
| `/release beta` | patch | `v1.7.4-beta` | Branch ready for testing before prod |
| `/release patch` | patch | `v1.7.4` | Bug fix going straight to prod |
| `/release minor` | minor | `v1.8.0` | Planned feature milestone |

### Typical flow — feature to prod

```bash
# On a feature branch — cut a test release
/release beta       # → v1.7.4-beta, pushes tag

# Merge to main, then promote
/release patch      # detects v1.7.4-beta on HEAD → promotes to v1.7.4
                    # Cloud Build triggers, deploys to Cloud Run
```

### Direct hotfix to prod

```bash
# On main
/release patch      # no beta on HEAD → bumps to v1.7.4 directly
```

The skill handles CHANGELOG updates, commits, annotated tags, and the push. It will confirm the version with you before making any changes.

## License

MIT
