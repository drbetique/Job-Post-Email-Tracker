# Roadmap

Planned work, roughly in the order I intend to do it.

## Reliability
- [ ] Retry with backoff on Google Sheets writes, which fail intermittently with SSL and network errors.
- [ ] Make a failed run resumable instead of reprocessing every message.

## Quality
- [ ] Unit tests for role detection, link extraction and CSV export.
- [ ] A CI job that byte-compiles the scripts and runs the tests on every push.
- [ ] Improve title extraction (schema.org and meta description) and truncate long titles sensibly.

## Features
- [ ] Support more job-alert senders than the single hard-coded Gmail query.
- [ ] Deduplicate postings that arrive from several senders, by canonical link.
- [ ] Track application status per posting in the sheet.
- [ ] Optional daily summary of new postings by role.

## Housekeeping
- [ ] Replace the hard-coded default sheet ID with required configuration.
- [ ] Cross-platform equivalents of the PowerShell helpers.
