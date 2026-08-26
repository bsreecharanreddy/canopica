#!/usr/bin/env bash
# Per-step wall-clock for one CI run, slowest first.
#
# Exists because the caching and runner-placement decisions in this
# directory were argued from measurements, and the next person to revisit
# them (including a later me) needs to be able to re-take the same
# measurement rather than trust a number pasted into a doc. Every timing
# quoted in docs/STATUS.md's CI-cost rows came from this script.
#
# Usage:  ./ci-step-timings.sh <run-id> [job-name-regex]
#   e.g.  ./ci-step-timings.sh 32935635062
#         ./ci-step-timings.sh 32935635062 'Eval-suite|End-to-end'
#
# Reports seconds per *step*, not per job, because that is the granularity
# the decisions are actually made at: a job that got faster because a step
# was removed and a job that got faster because the machine was less loaded
# look identical at job level and completely different here.
set -euo pipefail

run_id="${1:?usage: ci-step-timings.sh <run-id> [job-name-regex]}"
filter="${2:-.}"

gh run view "$run_id" --json jobs \
  | jq -r --arg filter "$filter" '
      .jobs[]
      | select(.name | test($filter))
      | . as $job
      | $job.steps[]
      | select(.startedAt != null and .completedAt != null)
      | ((.completedAt | fromdateiso8601) - (.startedAt | fromdateiso8601)) as $secs
      | select($secs > 0)
      | [$secs, $job.name, .name]
      | @tsv
    ' \
  | sort -rn \
  | awk -F'\t' '
      BEGIN { printf "%8s  %-32s %s\n", "SECONDS", "JOB", "STEP" }
      { total += $1; printf "%8d  %-32s %s\n", $1, substr($2, 1, 32), $3 }
      END { printf "%8s  %-32s\n", "-------", "--------------------------------"
            printf "%8d  %s\n", total, "TOTAL RUNNER-SECONDS" }
    '
