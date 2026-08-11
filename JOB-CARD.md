# JOB-CARD - Triage candidate messages

## The job (one sentence)

Given a single message from a candidate, decide what the sender wants:

one verdict out of a **closed list** of four: `interested`, `question`, `not_a_fit`, `other`.

## Why this job

FlyRank gets a lot of inbox mail. Some of it is spam/sales pitches, some of it
is questions, and some of it is real people who want the job. The hiring agent
from the earlier build week reads this inbox, and the first thing it does is
sort each message into a bucket so the right handler picks it up. That
decision is small, has a closed output, and a human can grade it in seconds.

## Input

- Free-form text: one candidate message, up to 2000 characters.

## Output

- A JSON object with a `verdict` (one of four enumerated values) and one or two
  short human-readable `reasons`.

## Rules

1. The verdict must always be exactly one of: `interested`, `question`,
   `not_a_fit`, `other`. Nothing else is a valid answer.
2. A message counts as `interested` when the sender wants the job, wants to
   apply, or asks how to start/apply. Questions about applying count as
   `interested`.
3. A message counts as `question` when the sender asks something about the
   role, the company, or the process but is not offering to apply.
4. A message counts as `not_a_fit` when the sender is selling something,
   promoting a service, or clearly writing to the wrong audience.
5. Everything that does not fit the other three categories is `other`.
6. `reasons` must be specific to the message, not generic boilerplate.

## When unsure

When a message falls between two categories, pick the category with the most
evidence in the message. If there is genuinely no evidence, pick `other`.
Never invent meaning that is not in the message.