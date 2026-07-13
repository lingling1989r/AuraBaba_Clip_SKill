# Validation Requirements

A job is not complete until the validation step passes.

## Copy validation

Validate the consolidated publish copy and the full article output.

Reject output when it:
- drifts away from the planned clip topics
- contains process language such as thinking, reasoning, internal notes, or handling steps
- includes filename-oriented wording or artifact suffixes in user-facing copy
- is empty or obviously malformed
- uses obvious technical jargon instead of plain user-facing language for the title
- produces headlines that are too short or too long for cover use

For structured short video titles:
- keep the main title short, readable, and cover-friendly
- preserve conflict, reversal,人物反差, or a direct anxiety-driving question instead of slogan wording
- podcast interview headlines may use the full format: main title, then a lane segment, then a guest-and-volume suffix
- the main title should stay concise and usually fit within about 20 visible characters
- the middle lane should summarize the niche track or core tension in one short phrase
- the ending suffix should standardize the series as `| 对话XX Vol XX` when guest metadata exists
- prefer plain user-facing language; AI can appear in the title, but obvious implementation jargon should not
- make the title feel specific, with visible pain point, turning point, niche identity, or concrete stakes

## Clip validation

Validate every rendered mp4 in `clips/`.

Check for:
- clip file exists
- ffprobe can read the file
- exactly one readable video stream exists
- duration is positive
- average frame rate is positive
- audio stream is present
- video codec metadata is present

This validation is meant to catch obvious broken exports, including clips that start normally and then behave like slow motion later.

## Status and artifacts

Validation should:
- run after `ops`
- write `ops/validation_report.json`
- set `status.json` to `completed` only after validation passes
- set `status.json` to `failed` if validation finds blocking issues
