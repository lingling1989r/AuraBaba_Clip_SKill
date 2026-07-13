# clipclipskill

Claude Code Skill MVP for long-video clipping.

This repository provides a local-first skill structure for:
- probing long videos
- extracting transcripts with Whisper-first tooling
- choosing scenario templates
- producing clip plans
- rendering clips into deterministic folders
- generating publishing copy for short-video operations

Input sources:
- local media files with `--video`
- YouTube or Bilibili URLs with `--url`

Main entrypoints:
- `Skill.md`
- `clipclipskill` CLI
- `scripts/` thin wrappers

Canonical flow:
- `clipclipskill --workspace-dir /path/to/output start-job ...`
- `clipclipskill --workspace-dir /path/to/output probe --job-id <job_id>`
- `clipclipskill --workspace-dir /path/to/output confirm-template --job-id <job_id> ...`
- `clipclipskill --workspace-dir /path/to/output transcribe --job-id <job_id>`
- `clipclipskill --workspace-dir /path/to/output plan --job-id <job_id>`
- `clipclipskill --workspace-dir /path/to/output approve-plan --job-id <job_id>`
- `clipclipskill --workspace-dir /path/to/output render --job-id <job_id>`
- `clipclipskill --workspace-dir /path/to/output ops --job-id <job_id>`

You can also set `CLIPCLIPSKILL_WORKSPACE=/path/to/output` to make all job folders and generated artifacts land in that directory.

If you want to avoid repeating the directory, bind it once:

```bash
clipclipskill bind-workspace /path/to/output
clipclipskill doctor
clipclipskill start-job --video /path/to/video.mp4 --template podcast_interview
clipclipskill probe --job-id <job_id>
```

Use `clipclipskill unbind-workspace` to clear that default.

At startup, each command checks the dependencies it needs before running. For URL jobs, `probe` downloads the source video into `<workspace-dir>/<job_id>/source/` first, then the rest of the pipeline reuses the downloaded local file.

Examples:

```bash
clipclipskill --workspace-dir /path/to/output start-job --video /path/to/video.mp4 --template podcast_interview
clipclipskill --workspace-dir /path/to/output probe --job-id <job_id>
```

```bash
clipclipskill start-job --url https://youtu.be/<video_id> --template podcast_interview
clipclipskill probe --job-id <job_id>
```

```bash
clipclipskill start-job --url https://www.bilibili.com/video/<bv_id> --template solo_course
clipclipskill probe --job-id <job_id>
```
