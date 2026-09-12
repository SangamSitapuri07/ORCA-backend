# ORCA — SYSTEM DESIGN
## Fisherman Safety & Livelihood Advisory System

> **Purpose:** Formal system-design document for the ORCA project, derived from the ORCA Phase 1 project constitution and the architecture recommendations established for Flutter, ORCA Box, RAG, multi-agent AI, local LLM inference, real-time updates, and Phase 2 Supabase integration.

---

# 1. System Design Overview

ORCA is an edge-first fisherman safety and livelihood advisory platform.

The system is divided into two primary runtime environments:

1. **Flutter Android APK** — the fisherman-facing client and judge/demo interface.
2. **ORCA Box** — the local/edge intelligence server containing the API, data ingestion, AI agents, RAG pipeline, GIS, local LLM, database, and alert engine.

An optional **Supabase cloud layer** is introduced only in Phase 2 for account, synchronization, history, feedback, and cloud-backed application data.

The core safety advisory path must remain functional without Supabase.

### Core architectural principle

```text
Flutter APK = Interface
ORCA Box   = Brain
Supabase   = Optional Cloud Memory (Phase 2)
```

---

# 2. System Design Goals

The architecture is designed around the following goals:

### 2.1 Safety-first decisions
Safety-critical verdicts are produced by the backend decision pipeline. The Flutter app does not independently recalculate scientific thresholds.

### 2.2 Provenance and honesty
Every numerical observation must carry its source and observation time. The system must never fabricate missing measurements.

### 2.3 Offline-first operation
The app must remain useful during connectivity loss by showing cached data with explicit freshness/staleness information.

### 2.4 Edge-first intelligence
Core AI, RAG, scientific data processing, GIS, and decision logic run on ORCA Box rather than depending on a cloud AI service.

### 2.5 Explainability
The AI tab exposes the collaboration trace of the 11 ORCA agents, while RAG exposes the evidence supporting important findings.

### 2.6 Graceful degradation
Failure of one provider, model, agent, or network path must produce an explicit degraded state rather than invented results.

### 2.7 Modular extensibility
Agents, data providers, screens, locales, and verdict definitions are registry-driven so new components can be added without rewriting unrelated features.

---

# 3. High-Level Architecture

```text
                         ┌───────────────────────────┐
                         │      External Sources     │
                         │                           │
                         │ Open-Meteo                │
                         │ INCOIS                    │
                         │ MOSDAC                    │
                         │ NOAA                      │
                         │ JTWC                      │
                         │ GFW                       │
                         │ Other configured sources  │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                         ORCA BOX                                 │
│                                                                  │
│  ┌──────────────┐      ┌──────────────────────────────────────┐  │
│  │ FastAPI      │─────▶│ Advisory / Decision Engine           │  │
│  │ /api/v1/*    │      │                                      │  │
│  │ SSE Stream   │      │ Validation → GIS → Analysis → Risk   │  │
│  └──────┬───────┘      └──────────────┬───────────────────────┘  │
│         │                             │                          │
│         │              ┌──────────────▼──────────────────────┐  │
│         │              │ Multi-Agent Orchestrator             │  │
│         │              │ 11 specialized agents               │  │
│         │              └──────────────┬──────────────────────┘  │
│         │                             │                          │
│         │              ┌──────────────▼──────────────────────┐  │
│         │              │ RAG + Local LLM                     │  │
│         │              │ Embeddings / Retrieval / Ollama      │  │
│         │              └──────────────┬──────────────────────┘  │
│         │                             │                          │
│         │        ┌────────────────────▼─────────────────────┐   │
│         │        │ PostgreSQL + PostGIS + Cache             │   │
│         │        └──────────────────────────────────────────┘   │
│         │                                                        │
│         │        ┌──────────────────────────────────────────┐   │
│         └───────▶│ Alert Engine + SSE Event Generator      │   │
│                  └──────────────────────────────────────────┘   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                         HTTP + SSE
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FLUTTER APK                               │
│                                                                  │
│ Home │ Map │ AI │ Alerts │ Navigate │ Info                       │
│                                                                  │
│ Riverpod → UseCases → Repository → Remote / Cache                │
│                                                                  │
│ Offline cache + POST outbox + SSE reconnect                      │
└──────────────────────────────────────────────────────────────────┘

                    Phase 2 Optional Cloud Sidecar
                                │
                                ▼
                    ┌────────────────────────┐
                    │       Supabase         │
                    │ Auth / Sync / History  │
                    │ Feedback / Storage     │
                    └────────────────────────┘
```

---

# 4. Logical Layered Architecture

ORCA follows six logical layers.

## 4.1 Presentation Layer

Responsible for:

- Flutter screens
- Widgets
- Animations
- Maps
- Charts
- Verdict cards
- Agent trace UI
- Alert banners
- Localization
- Loading/error/empty states

Widgets must not directly call Dio, Hive, SSE, or backend endpoints.

---

## 4.2 Application Layer

Responsible for application use cases.

Examples:

```text
GetCurrentAdvisory
GetZoneAdvisory
GetGridData
GetRouteAdvisory
GetAgentTrace
GetAlerts
SendFeedback
ConnectLiveStream
```

Typical flow:

```text
Widget
  ↓
Riverpod Provider / AsyncNotifier
  ↓
UseCase
  ↓
Repository Interface
```

---

## 4.3 AI / Decision Layer

Responsible for:

- Agent orchestration
- RAG retrieval
- Local LLM inference
- Ocean analysis
- Satellite interpretation
- Weather hazard analysis
- Marine ecology reasoning
- Fisheries/PFZ reasoning
- Anomaly detection
- Marine risk calculation
- Final advisory synthesis

The final safety verdict is authoritative from the backend.

---

## 4.4 Data Layer

Responsible for:

- DTOs
- Repository implementations
- API clients
- Local cache
- PostgreSQL
- PostGIS
- Data normalization
- Provenance records
- RAG documents/chunks
- Alert state

---

## 4.5 Ingestion Layer

Responsible for:

- External provider adapters
- Fetching source data
- Normalization
- Validation
- Quality checks
- Timestamping
- Storing observations
- Updating indexes

---

## 4.6 Infrastructure Layer

Responsible for:

- ORCA Box runtime
- Ollama/local LLM
- FastAPI
- PostgreSQL/PostGIS
- Network connectivity
- Logging
- Health monitoring
- SSE
- Configuration

---

# 5. Flutter Android APK Architecture

The Flutter application is a genuine Android client rather than a web wrapper.

## 5.1 Runtime structure

```text
Flutter Widget
      │
      ▼
Riverpod Provider / AsyncNotifier
      │
      ▼
UseCase
      │
      ▼
Repository Interface
      │
      ├───────────────┐
      ▼               ▼
Remote Data        Local Cache
      │               │
      ▼               ▼
   ORCA Box       Hive / Local Store
```

The UI receives domain-level results and should not know whether a value came from the network or cache.

---

## 5.2 Repository boundary

A repository interface creates a clean boundary for Phase 2.

```text
AdvisoryRepository
        │
        ├── OrcaBoxAdvisoryRepository
        │
        └── Future Cloud/Sync Repository
```

This allows Supabase to be added later without replacing the UI architecture.

---

# 6. ORCA Box Architecture

ORCA Box is the computational brain.

## 6.1 Core components

```text
ORCA Box
│
├── FastAPI
│   ├── REST API
│   └── SSE live stream
│
├── Advisory Engine
│
├── Multi-Agent Engine
│
├── RAG Engine
│
├── Local LLM Runtime
│   └── Ollama
│
├── GIS Engine
│
├── Data Provider Layer
│
├── PostgreSQL
│
├── PostGIS
│
├── Cache
│
└── Alert Engine
```

Heavy computation should remain on ORCA Box so that the Android device stays responsive and energy-efficient.

---

# 7. External Data Ingestion Architecture

The app never directly calls scientific providers.

```text
External Provider
       │
       ▼
Provider Adapter
       │
       ▼
Raw Observation
       │
       ▼
Normalization
       │
       ▼
Data Validation / QC
       │
       ├───────────────┐
       ▼               ▼
PostgreSQL/PostGIS   RAG Index
       │               │
       ├───────┬───────┘
       ▼       ▼
   Advisory   AI Agents
```

Each provider adapter should preserve:

- Source name
- Dataset/product name
- Observation timestamp
- Retrieval timestamp
- Geographic coverage
- Units
- Original/reference identifier
- Quality status

If a source fails, its state should be represented explicitly.

---

# 8. Data Quality and Validation

The `data_validation` agent is deterministic.

It verifies:

- Required fields
- Missing values
- Units
- Geographic validity
- Timestamp validity
- Range checks
- Provider freshness
- Duplicate observations
- Contradictory source data where applicable

The system must distinguish:

```text
Fresh
Recent
Stale
Unreachable
Invalid
Missing
```

A stale value must never be silently presented as current.

---

# 9. RAG Architecture

RAG is used to ground AI reasoning in relevant source material.

## 9.1 RAG pipeline

```text
User Query / Advisory Context
            │
            ▼
      Query Processing
            │
       ┌────┴────┐
       ▼         ▼
 Semantic      Keyword
 Retrieval     Retrieval
       │         │
       └────┬────┘
            ▼
       Candidate Set
            │
            ▼
         Reranking
            │
            ▼
    Relevant Evidence
            │
            ▼
      Context Builder
            │
            ▼
       Agent / LLM
            │
            ▼
 Evidence-backed Finding
```

---

## 9.2 Evidence object

Every retrieved evidence item should preserve metadata such as:

```text
source
dataset
timestamp
location
document/chunk identifier
relevance score
content
```

The final explanation should make it possible to determine where important information came from.

---

## 9.3 RAG does not replace live data

RAG provides contextual knowledge and supporting evidence.

Live scientific observations remain part of the data-provider pipeline.

```text
Live data → current conditions
RAG       → supporting knowledge/context
```

The two should not be conflated.

---

# 10. Multi-Agent Architecture

ORCA uses 11 agents.

| Agent | Type | Responsibility |
|---|---|---|
| `data_validation` | Deterministic | Validate incoming data |
| `gis_spatial` | Deterministic | Spatial/geographic reasoning |
| `ocean_analysis` | LLM | Analyze ocean conditions |
| `satellite_analysis` | LLM | Analyze satellite-derived information |
| `weather_hazard` | LLM | Analyze weather hazards |
| `map_synoptic` | Deterministic | Prepare synoptic map information |
| `marine_ecology` | LLM | Interpret ecological conditions |
| `fisheries_pfz` | LLM | Fisheries/PFZ reasoning |
| `marine_risk` | Deterministic | Calculate marine risk |
| `anomaly_detection` | Deterministic | Detect unusual conditions |
| `orchestrator` | LLM | Coordinate and synthesize results |

---

# 11. Agent Communication

Agents should exchange structured messages rather than unstructured conversational text.

Conceptual message:

```text
AgentMessage
├── run_id
├── agent_id
├── task
├── input_context
├── findings
├── confidence
├── evidence[]
├── warnings[]
├── status
└── timestamp
```

Possible statuses:

```text
queued
running
completed
degraded
failed
skipped
```

This makes the AI tab a real representation of backend execution rather than a simulated animation.

---

# 12. Advisory Decision Pipeline

A complete advisory request follows this sequence:

```text
Fisher Location / Zone
        │
        ▼
Flutter App
        │
        ▼
/api/v1/advisory
        │
        ▼
Data Validation
        │
        ▼
GIS Spatial Checks
        │
        ├───────────────┐
        ▼               ▼
Ocean Analysis      Weather Hazard
        │               │
        ├───────┬───────┘
        ▼       ▼
Satellite    Synoptic Map
        │       │
        └───┬───┘
            ▼
          RAG
            │
            ▼
 ┌───────────────────────────┐
 │ Marine Ecology            │
 │ Fisheries / PFZ           │
 │ Anomaly Detection         │
 └─────────────┬─────────────┘
               ▼
        Marine Risk Agent
               │
               ▼
       Worst-case Fold
               │
               ▼
       Final Verdict
               │
               ▼
      Provenance Assembly
               │
               ▼
          FastAPI
               │
               ▼
          Flutter App
```

---

# 13. Verdict Architecture

The backend owns the safety thresholds and final verdict.

Reference thresholds defined by the project constitution include:

```text
Wave height:
< 2.5 m       → Good
≥ 2.5 m       → Caution
≥ 4.0 m       → Danger

Gust:
≥ 34 kn       → Danger

Sustained wind:
≥ 20 kn       → Caution

Surface current:
> 3 kn         → Note
```

Route land verification is also part of route safety.

The application should not independently recreate these rules.

---

# 14. Worst-Case Decision Fold

Safety should not be averaged across risks.

Conceptually:

```text
Ocean Risk       ─┐
Weather Risk     ─┤
Current Risk     ─┤
Route Risk       ─┤──▶ Worst-case Fold ──▶ Final Verdict
Anomaly Risk     ─┤
Other Risk       ─┘
```

For example:

```text
Ocean     = GOOD
Weather   = GOOD
Route     = CAUTION
Current   = GOOD

Final     = CAUTION
```

A severe hazard should therefore not be hidden by several safe observations.

---

# 15. Provenance Architecture

Every important numerical output must carry provenance.

Conceptual structure:

```text
Observation
├── value
├── unit
├── source
├── dataset
├── observed_at
├── retrieved_at
├── location
└── freshness
```

Flutter should display:

```text
Wave Height
2.1 m

Source: <source>
Observed: <time>
Status: Fresh
```

If unavailable:

```text
Wave Height
Unavailable

Reason: Provider unreachable
```

Never:

```text
Wave Height
2.1 m
```

with no source or freshness information.

---

# 16. Real-Time SSE Architecture

ORCA uses Server-Sent Events for live backend-to-app updates.

```text
Provider Update
      │
      ▼
Data Ingestion
      │
      ▼
Risk / Alert Engine
      │
      ▼
Event Generator
      │
      ▼
/api/live/stream
      │
      ▼
Flutter SSE Client
      │
      ├──▶ Home
      ├──▶ Alerts
      ├──▶ Map
      └──▶ AI Trace
```

Example event categories:

```text
advisory_update
risk_change
alert
agent_started
agent_completed
provider_status
system_status
```

The stream should support reconnect behavior.

---

# 17. Offline-First Architecture

Offline support is a core Phase 1 requirement.

## 17.1 GET flow

```text
Request
  │
  ▼
Local Cache
  │
  ├── Has cached value ──▶ Display immediately
  │                         + freshness badge
  │
  └── No cached value ──▶ Request ORCA Box
                              │
                              ▼
                           Cache result
                              │
                              ▼
                           Display
```

---

## 17.2 POST flow

For operations such as feedback:

```text
User Action
    │
    ▼
Try Network
    │
    ├── Success ──▶ Complete
    │
    └── Failure
          │
          ▼
       Outbox
          │
          ▼
    Retry on reconnect
```

---

## 17.3 Staleness

Cached information must show age.

Example:

```text
Last advisory
Updated 18 min ago
RECENT
```

or:

```text
Last advisory
Updated 9 hr ago
STALE
```

Offline does not mean pretending that old data is current.

---

# 18. Failure and Graceful Degradation Architecture

ORCA explicitly models failure.

## 18.1 External provider failure

```text
Provider
   │
   X
   ▼
Provider Adapter
   │
   ▼
Status = UNREACHABLE
   │
   ├── Use valid cached observation if allowed
   │
   └── Otherwise mark data unavailable
```

---

## 18.2 Agent failure

```text
Agent A ──▶ Completed
Agent B ──▶ Failed
Agent C ──▶ Completed
             │
             ▼
       Orchestrator
             │
             ▼
    Degraded / limited result
```

The system should identify which component failed.

---

## 18.3 Backend unavailable

The Flutter app must show:

```text
ORCA Box unavailable
Showing last known advisory
```

It must not manufacture a new advisory locally.

---

# 19. Alert Architecture

Alerts are generated by the backend.

```text
Live Observation
      │
      ▼
Validation
      │
      ▼
Risk Evaluation
      │
      ▼
Alert Engine
      │
      ├── No threshold crossing → No alert
      │
      └── Threshold crossing
                 │
                 ▼
              Alert
                 │
                 ▼
               SSE
                 │
                 ▼
            Flutter App
```

The Phase 1 application can surface alerts in the Alerts tab and through appropriate in-app UI.

---

# 20. Map and GIS Architecture

GIS processing occurs on ORCA Box.

```text
Location
   │
   ▼
GIS Spatial Agent
   │
   ├── Coast / land verification
   ├── Zone membership
   ├── Spatial constraints
   └── Route checks
          │
          ▼
     PostGIS
          │
          ▼
     Map Response
          │
          ▼
      Flutter Map
```

The Flutter map is primarily a visualization and interaction layer.

It should not become the authoritative GIS engine.

---

# 21. Route Advisory Architecture

Route safety uses both geometry and environmental conditions.

```text
Origin
  │
  ▼
Destination / Fishing Area
  │
  ▼
Route Generation
  │
  ▼
Land / Coast Verification
  │
  ▼
Environmental Risk Along Route
  │
  ▼
Route Advisory
  │
  ▼
Flutter Navigate Screen
```

A route that crosses land or violates configured spatial constraints must not be presented as a safe marine route.

---

# 22. Phase 2 Supabase Architecture

Supabase is a complementary cloud layer, not the replacement for ORCA Box.

## 22.1 Appropriate Supabase responsibilities

Phase 2 can use Supabase for:

- Authentication
- User profiles
- Saved fishing locations
- Advisory history synchronization
- Feedback synchronization
- Catch/livelihood reports
- Cloud document/storage features
- Selective application telemetry

---

## 22.2 What Supabase should not own

Supabase should not become the primary runtime for:

- Local LLM inference
- Core RAG reasoning
- The 11-agent orchestration engine
- Scientific provider aggregation
- GIS-heavy processing
- Safety-critical verdict generation

The authoritative live advisory path remains:

```text
Flutter
   ↓
ORCA Box
   ↓
Scientific Data + Agents + RAG + Decision Engine
```

---

# 23. Phase 2 Cloud Sync Architecture

```text
                    ┌──────────────────┐
                    │     Supabase     │
                    │ Auth / Profiles  │
                    │ History / Sync   │
                    │ Feedback/Storage │
                    └────────▲─────────┘
                             │
                         Sync Layer
                             │
┌──────────────┐         ┌───┴────┐
│ Flutter APK  │────────▶│ Local  │
│              │         │ State  │
└──────┬───────┘         └────────┘
       │
       │ Safety / Advisory
       ▼
┌────────────────┐
│   ORCA Box     │
│ authoritative  │
│ advisory path  │
└────────────────┘
```

Cloud synchronization must never block the core safety advisory path.

---

# 24. Security Boundaries

## 24.1 Flutter

The APK should contain:

- No provider API secrets
- No LLM provider secrets
- No hardcoded production IP
- No database credentials

The ORCA Box base URL is configurable.

---

## 24.2 ORCA Box

Provider credentials and sensitive configuration remain server-side.

```text
Flutter
  │
  │ public application API
  ▼
ORCA Box
  │
  │ private provider credentials
  ▼
External Sources
```

---

## 24.3 Supabase Phase 2

Supabase credentials and access policies should follow the platform's authentication and row-level authorization model.

Cloud synchronization should be isolated from safety-critical decision computation.

---

# 25. Performance Architecture

The Android client should remain lightweight.

### Flutter responsibilities

- Rendering
- Map interaction
- Local cache reads
- Small data transformations
- SSE event handling
- UI animation

### ORCA Box responsibilities

- AI inference
- RAG
- Data ingestion
- GIS computation
- Large data processing
- Agent orchestration
- Decision computation

This prevents expensive workloads from blocking the phone UI.

---

# 26. UI and Interaction Architecture

The UI has two audiences:

### Fisher-facing mode

Optimized for:

- Low literacy
- Bright sunlight
- Large touch targets
- Simple language
- Telugu / Hindi / English
- Icon + shape + colour
- Minimal cognitive load

Example:

```text
┌──────────────────────────────┐
│       CAN I GO?              │
│                              │
│          CAUTION             │
│                              │
│ Waves are moderate.          │
│ Check the route before       │
│ going farther offshore.      │
│                              │
│ Updated: 12 min ago          │
└──────────────────────────────┘
```

### Judge / technical mode

Provides:

- Agent trace
- Source provenance
- RAG evidence
- Provider status
- Model/runtime information
- Data freshness
- Decision pipeline

---



# 26A. Current UI Philosophy — Simple, Elegant, and Fisher-First

> **Important current requirement:** The ORCA UI should be extremely simple and elegant for the current phase. Do not make the application visually fancy, feature-heavy, or unnecessarily descriptive.

The current goal is **usability before visual complexity**.

ORCA is intended to be usable by fishers who may have low literacy or limited experience with smartphone applications. Therefore, the interface should feel immediately understandable without requiring the user to read long explanations, understand technical terminology, or navigate complicated menus.

## 26A.1 Core UI principle

```text
LESS UI
  +
LESS TEXT
  +
LESS CHOICES
  +
CLEAR ICONS
  +
CLEAR ACTIONS
  =
EASIER FOR EVERYONE
```

The application should not try to impress the user with complex UI components.

For the current version:

- Keep screens clean.
- Keep the number of actions small.
- Show only information that is necessary.
- Use large, obvious buttons.
- Prefer familiar icons and symbols.
- Use short plain-language statements.
- Avoid technical terminology on fisherman-facing screens.
- Avoid long paragraphs.
- Avoid complicated forms.
- Avoid nested menus.
- Avoid unnecessary settings.
- Avoid excessive cards, tabs, controls, filters, and configuration options.
- Avoid decorative animations that do not improve usability.

---

## 26A.2 Illiterate / low-literacy usability

The app should be designed so that a user with very limited reading ability can understand the primary action.

The interface should communicate primarily through:

```text
ICON
  +
COLOUR
  +
SHAPE
  +
VERY SHORT TEXT
```

Colour must not be the only indicator.

For example:

```text
┌─────────────────────────┐
│                         │
│          ⚠              │
│                         │
│        CAUTION          │
│                         │
│     Check weather       │
│                         │
│      [ GO BACK ]        │
│                         │
└─────────────────────────┘
```

The user should not need to understand terms such as:

```text
API
RAG
LLM
PostGIS
SSE
ensemble
anomaly score
vector embedding
```

Those belong to the technical/judge-facing side of the system, not the primary fisherman experience.

---

## 26A.3 Minimal navigation

The current app should retain the defined major areas:

```text
Home
Map
AI
Alerts
Navigate
Info
```

However, the presence of these sections does **not** mean every screen should expose many controls.

The Home screen should remain the simplest and most important screen.

A fisherman should be able to open the app and quickly answer:

```text
CAN I GO?
```

The answer should be immediately visible.

---

## 26A.4 Home screen priority

The Home screen should prioritize:

1. Current safety verdict.
2. One short explanation.
3. Freshness/age of the information.
4. One obvious next action.

Conceptually:

```text
┌─────────────────────────────┐
│ ORCA                         │
│                             │
│        ⚠ CAUTION            │
│                             │
│        Waves are high.       │
│                             │
│        Updated 12 min ago   │
│                             │
│       [ CHECK ROUTE ]       │
│                             │
└─────────────────────────────┘
```

Do not place multiple competing calls-to-action on the primary Home screen.

---

## 26A.5 No over-description

The system may contain sophisticated AI reasoning internally, but the fisherman-facing UI should not expose all of that complexity.

Instead of:

```text
The marine risk assessment indicates elevated
hazard probability due to the interaction between
significant wave height, wind gust distribution,
surface current velocity and route geometry...
```

prefer:

```text
⚠ Strong waves today.
Check your route before going.
```

The detailed reasoning can remain available in the **AI** section for judges and technical users.

---

## 26A.6 No unnecessary options

Avoid interfaces such as:

```text
Choose analysis type
Choose model
Choose data source
Choose agent
Choose confidence level
Choose forecast horizon
Choose map layer
Choose retrieval mode
Choose reasoning mode
```

unless a particular option is genuinely required by the user's task.

The application should make sensible decisions automatically.

```text
User
  ↓
Simple request
  ↓
ORCA decides what is required
  ↓
Simple answer
```

The complexity belongs inside ORCA Box, not in front of the fisherman.

---

## 26A.7 Elegant does not mean fancy

The desired design is:

```text
Simple
Clean
Calm
Readable
Consistent
Professional
```

Not:

```text
Over-animated
Crowded
Gamified
Decorative
Neon-heavy
Dashboard-like
Technically intimidating
```

Animations should be subtle and purposeful.

For example:

- Smooth page transitions.
- Small state transitions.
- Gentle loading indicators.
- Clear alert appearance.
- Map movement that feels natural.

Do not use animation merely because it is technically possible.

---

## 26A.8 Progressive disclosure

Advanced information should appear only when the user intentionally asks for it.

```text
                 SIMPLE
                   │
                   ▼
              HOME VERDICT
                   │
            User wants more?
                   │
                   ▼
             Basic details
                   │
            User wants more?
                   │
                   ▼
          AI / Evidence / Trace
```

This keeps the primary experience simple while still allowing judges and technical users to inspect the intelligence underneath.

---

## 26A.9 Current-phase UI rule

For the current implementation:

> **Build the simplest usable version first.**

Do not add:

- Fancy dashboards.
- Complex charts everywhere.
- Excessive animations.
- Multiple modes.
- Large configuration panels.
- Complicated onboarding.
- Unnecessary personalization.
- Decorative information cards.
- Long explanations.
- Advanced controls that a fisherman does not need.

The sophisticated architecture should exist **behind** a very simple interface.

---

## 26A.10 Design target

The ideal reaction from a first-time fisherman should be:

> **"I opened it and immediately understood what it is telling me."**

The ideal reaction from a judge should be:

> **"The interface is simple, but the system underneath is sophisticated."**

That separation is intentional.


# 27. AI Trace Architecture

The AI tab should represent actual backend agent events.

```text
Orchestrator
     │
     ├── Data Validation       ✓
     ├── GIS Spatial           ✓
     ├── Ocean Analysis        ✓
     ├── Weather Hazard        ✓
     ├── Satellite Analysis   ✓
     ├── Marine Ecology        ✓
     ├── Fisheries / PFZ       ✓
     ├── Anomaly Detection    ✓
     └── Marine Risk           ✓
              │
              ▼
        Final Synthesis
```

Each event can expose:

- Agent
- Status
- Duration
- Finding
- Evidence
- Warning
- Timestamp

The app must not fake agent activity merely for visual effect.

---

# 28. Model Runtime Architecture

The system is designed for local LLM inference through Ollama.

```text
Agent
  │
  ▼
Prompt / Structured Context
  │
  ▼
Ollama
  │
  ▼
Local LLM
  │
  ▼
Structured Agent Output
  │
  ▼
Orchestrator
```

Deterministic tasks should remain deterministic.

The LLM should not be used to replace straightforward calculations such as threshold comparison, spatial validation, or anomaly rules where deterministic logic is appropriate.

---

# 29. Observability Architecture

The system should expose enough information to debug and explain an advisory.

Recommended identifiers:

```text
request_id
advisory_id
agent_run_id
source_observation_id
alert_id
```

Useful observability information includes:

- Request timing
- Provider status
- Agent status
- Agent duration
- RAG retrieval count
- Evidence identifiers
- Model/runtime status
- Cache state
- Final verdict
- Failure reason

This supports both engineering debugging and judge-facing explainability.

---

# 30. Health Architecture

The backend exposes health information through:

```text
/health
```

Health status should distinguish system components such as:

```text
API             OK
Database        OK
PostGIS         OK
LLM Runtime     OK
RAG             OK
Provider A      OK
Provider B      UNREACHABLE
SSE             OK
```

A single failed provider should not necessarily make the entire ORCA Box unavailable.

---

# 31. API Architecture

The application communicates with ORCA Box through the versioned API.

Core routes include:

```text
/api/v1/health
/api/v1/advisory
/api/v1/zone
/api/v1/grid
/api/v1/reason
/api/v1/field
/api/v1/route-check
/api/v1/route-advisory
/api/v1/tiles
/api/v1/layers
/api/v1/datasets
/api/v1/zones
/api/v1/alerts
/api/v1/agents
/api/v1/chat
/api/v1/feedback
```

Live communication:

```text
/api/live/stream
```

Synoptic map:

```text
/api/map/synoptic
```

Legacy fallback, if required by the existing project contract, should remain centralized in the API path configuration rather than scattered throughout the app.

---

# 32. Advisory Request Sequence

```text
Fisher
 │
 │ Open Home
 ▼
Flutter
 │
 │ Request advisory
 ▼
Repository
 │
 ▼
ORCA Box API
 │
 ▼
Validate request
 │
 ▼
Fetch current observations
 │
 ▼
Run deterministic agents
 │
 ▼
Run analytical agents
 │
 ▼
Retrieve RAG evidence
 │
 ▼
Run marine risk
 │
 ▼
Worst-case fold
 │
 ▼
Build provenance
 │
 ▼
Return advisory
 │
 ▼
Flutter
 │
 ├── Verdict
 ├── Conditions
 ├── Source
 ├── Freshness
 └── Explanation
```

---

# 33. Live Alert Sequence

```text
External Data Update
        │
        ▼
Provider Adapter
        │
        ▼
Validation
        │
        ▼
Risk Engine
        │
        ▼
Threshold / Event Detection
        │
        ▼
Alert Engine
        │
        ▼
SSE Event
        │
        ▼
Flutter
        │
        ├── Alerts tab
        ├── Home warning
        └── Map state
```

---

# 34. End-to-End System Data Flow

```text
                 DATA SOURCES
                     │
                     ▼
             ┌───────────────┐
             │ Provider      │
             │ Adapters      │
             └───────┬───────┘
                     ▼
             ┌───────────────┐
             │ Normalize +   │
             │ Validate      │
             └───────┬───────┘
                     ▼
        ┌────────────────────────┐
        │ PostgreSQL / PostGIS   │
        └───────────┬────────────┘
                    │
             ┌──────┴───────┐
             ▼              ▼
          RAG Index      Decision Engine
             │              │
             ▼              ▼
          LLM Agents ◀── Orchestrator
             │              │
             └──────┬───────┘
                    ▼
              Marine Risk
                    │
                    ▼
              Final Verdict
                    │
             ┌──────┴──────┐
             ▼             ▼
        REST API          SSE
             │             │
             └──────┬──────┘
                    ▼
               Flutter APK
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
       Home        Map          AI
        │           │            │
        ▼           ▼            ▼
     Alerts      Navigate       Info
```

---

# 35. System Design Invariants

The following rules are architectural invariants.

### Invariant 1 — Backend verdict is authoritative

Flutter does not independently override the backend safety verdict.

### Invariant 2 — Every number has provenance

Every important numerical observation includes source and time.

### Invariant 3 — No fabricated data

Unavailable information remains unavailable.

### Invariant 4 — Stale data is visibly stale

Cached information is never silently presented as current.

### Invariant 5 — AI activity must be real

The AI trace reflects actual agent execution.

### Invariant 6 — Deterministic logic stays deterministic

Safety thresholds and spatial checks should not be delegated unnecessarily to an LLM.

### Invariant 7 — Core safety does not depend on Supabase

Phase 2 cloud services are complementary.

### Invariant 8 — External sources are accessed by ORCA Box

Flutter does not directly aggregate scientific providers.

### Invariant 9 — UI does not contain infrastructure logic

Widgets never directly call Dio, Hive, or backend services.

### Invariant 10 — No hardcoded deployment addresses

The ORCA Box base URL is configurable.

---

# 36. Recommended Project Boundary

```text
                         ORCA PROJECT
                              │
             ┌────────────────┴────────────────┐
             │                                 │
             ▼                                 ▼
       Flutter APK                         ORCA Box
             │                                 │
      Presentation                       FastAPI API
      Application                        Decision Engine
      Local Cache                        Multi-Agent AI
      SSE Client                         RAG
      Offline Outbox                     Ollama
      Maps                               PostgreSQL
      Localization                       PostGIS
                                         Providers
                                         Alert Engine
             │                                 │
             └──────────────┬──────────────────┘
                            │
                       Phase 2 only
                            ▼
                         Supabase
                    Auth / Sync / Storage
```

---

# 37. Deployment Model

## Phase 1

```text
Android Phone
     │
     │ Wi-Fi / Hotspot / LAN / Tunnel
     ▼
ORCA Box
     │
     ├── FastAPI
     ├── Agents
     ├── RAG
     ├── Ollama
     ├── PostgreSQL/PostGIS
     ├── Providers
     └── Alert Engine
```

No mandatory cloud dependency.

## Phase 2

```text
Android Phone
     │
     ├──────────────▶ ORCA Box
     │                  │
     │                  └── Scientific / AI truth
     │
     └──────────────▶ Supabase
                        │
                        └── User/cloud application data
```

---

# 38. Final Target Architecture

```text
                             ┌───────────────────────────┐
                             │       DATA SOURCES        │
                             │                           │
                             │ Weather • Ocean •         │
                             │ Satellite • Fisheries •   │
                             │ Marine / Spatial Sources  │
                             └─────────────┬─────────────┘
                                           │
                                           ▼
                             ┌───────────────────────────┐
                             │    INGESTION & QUALITY    │
                             │                           │
                             │ Adapters • Normalization  │
                             │ Validation • Freshness    │
                             └─────────────┬─────────────┘
                                           │
                                           ▼
              ┌─────────────────────────────────────────────────┐
              │                    ORCA BOX                      │
              │                                                 │
              │  ┌───────────────┐    ┌──────────────────────┐ │
              │  │ FastAPI       │───▶│ Advisory Engine      │ │
              │  │ REST + SSE    │    └──────────┬───────────┘ │
              │  └───────────────┘               │             │
              │                                  ▼             │
              │                       ┌──────────────────────┐ │
              │                       │ 11-Agent System      │ │
              │                       │                      │ │
              │                       │ Validation           │ │
              │                       │ GIS                  │ │
              │                       │ Ocean                │ │
              │                       │ Satellite            │ │
              │                       │ Weather              │ │
              │                       │ Synoptic             │ │
              │                       │ Ecology              │ │
              │                       │ Fisheries/PFZ        │ │
              │                       │ Anomaly              │ │
              │                       │ Marine Risk           │ │
              │                       │ Orchestrator          │ │
              │                       └──────────┬───────────┘ │
              │                                  │             │
              │                     ┌────────────▼───────────┐ │
              │                     │ RAG + Ollama           │ │
              │                     └────────────┬───────────┘ │
              │                                  │             │
              │                     ┌────────────▼───────────┐ │
              │                     │ PostgreSQL + PostGIS    │ │
              │                     └────────────┬───────────┘ │
              │                                  │             │
              │                     ┌────────────▼───────────┐ │
              │                     │ Alert / Event Engine    │ │
              │                     └─────────────────────────┘ │
              └──────────────────────────────┬──────────────────┘
                                             │
                                      HTTP + SSE
                                             │
                                             ▼
              ┌─────────────────────────────────────────────────┐
              │                    FLUTTER APK                  │
              │                                                 │
              │ Home │ Map │ AI │ Alerts │ Navigate │ Info     │
              │                                                 │
              │ Riverpod • UseCases • Repositories              │
              │ Hive Cache • Outbox • SSE • Localization        │
              └──────────────────────────────┬──────────────────┘
                                             │
                                             │ Phase 2
                                             ▼
                              ┌──────────────────────────┐
                              │         SUPABASE         │
                              │                          │
                              │ Auth • Profiles • Sync   │
                              │ History • Feedback       │
                              │ Reports • Storage        │
                              └──────────────────────────┘
```

---

# 39. Architecture Summary

ORCA should remain **edge-first, evidence-backed, agent-driven, and offline-first**.

The intended responsibility split is:

| Component | Primary Responsibility |
|---|---|
| Flutter APK | User experience, visualization, local cache, offline behavior |
| ORCA Box | Core intelligence and authoritative advisory computation |
| FastAPI | Stable application API |
| Agents | Specialized analysis and orchestration |
| RAG | Evidence retrieval and contextual grounding |
| Ollama | Local LLM inference |
| PostgreSQL | Structured data |
| PostGIS | Spatial data and GIS queries |
| Provider adapters | Scientific data ingestion |
| Alert Engine | Threshold/event-driven warnings |
| SSE | Real-time backend-to-app updates |
| Supabase Phase 2 | Authentication, synchronization, history, feedback, and cloud application data |

The architecture therefore preserves a strong Phase 1 demonstration while leaving a clean path to a production-oriented Phase 2 system.

**Final principle:**

```text
              CURRENT TRUTH
                   │
            Scientific Sources
                   │
                   ▼
                ORCA Box
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
      GIS         RAG         Agents
       │           │           │
       └───────────┼───────────┘
                   ▼
             Marine Risk
                   │
                   ▼
            Final Verdict
                   │
                   ▼
              Flutter APK
                   │
                   ▼
             Fisher / Judge
```

This is the target system design for ORCA Phase 1, with Supabase reserved as an optional Phase 2 cloud extension.
