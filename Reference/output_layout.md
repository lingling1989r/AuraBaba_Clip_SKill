# Output Layout

All job outputs live under `runtime/jobs/<job_id>/`.

## Final deliverables

- `clips/<topic>_<seq>.mp4`
- `ops/publish_manifest.json`
- `ops/publish_copy.json`
- `ops/publish_copy.md`
- `ops/full_article.json`
- `ops/full_article.md`
- `ops/full_article.docx`
- `ops/full_article.pdf`
- `ops/validation_report.json`

## Intermediate artifacts

- `planning_package/clip_plan.v1.json`
- `planning_package/clip_artifacts/<topic>_<seq>.srt`
- `planning_package/clip_artifacts/<topic>_<seq>.json`

## Rules

- `clips/` only keeps final mp4 files.
- Clip subtitles and clip manifests are intermediate artifacts, not final deliverables.
- Ops materials are generated once per job and stay under `ops/`.
- Do not create one subdirectory per clip unless a future requirement explicitly needs it.
- `ops/validation_report.json` must exist before the job is considered complete.
- Deliverable copy must stay on-topic and must not contain process text, thinking text, internal handling notes, or filename-oriented wording.
- Clip validation must screen for obvious playback integrity problems, especially exports that later behave like slow motion after the opening seconds.
