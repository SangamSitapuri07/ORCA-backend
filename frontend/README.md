# ORCA Flutter Android Client

The genuine Android interface for the ORCA Box. Feature code follows the existing layered flow:

```text
screen/widget → Riverpod provider → use case → repository → Dio/SSE datasource
```

The APK displays backend-authoritative safety decisions and does not recompute scientific thresholds. Missing measurements remain unavailable; cache timestamps and staleness remain visible.

```bash
flutter pub get
flutter gen-l10n
flutter analyze
flutter test
flutter run --dart-define=ORCA_API_BASE_URL=https://your-orca-box.example
```

HTTP ORCA Box URLs are accepted only in debug builds. Release builds target Android API 36, require HTTPS, and need a deployment signing configuration.

The production client contains no scientific demo fixtures: failed ORCA Box or provider calls remain explicit unavailable/error states. A drill-alert control appears only when the connected backend reports that `ORCA_DEMO_MODE=1` is enabled, and every generated item is labelled as simulated. Supabase Phase-2 persistence/auth, cloud advisory history, catch upload, and fleet aggregation are explicitly unavailable because the authoritative team implementation was not supplied. Core ORCA Box safety remains independent of those features.

See the repository root `README.md` for backend setup, environment variables, architecture, tests, and blockers.
