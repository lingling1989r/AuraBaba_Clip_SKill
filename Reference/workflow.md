# Workflow

1. Intake video path and user preferences.
2. Probe video metadata and estimate processing time.
3. Require template and strategy confirmation.
4. Run transcription and optional diarization.
5. Build clip candidates and clip plan package.
6. Require clip-plan confirmation.
7. Render final mp4 clips into `clips/` with topic-based names.
8. Write per-clip subtitle and manifest files into `planning_package/clip_artifacts/`.
9. Generate one consolidated publishing package under `ops/`.
10. Run final validation on copy quality and clip playback integrity before marking the job completed.
