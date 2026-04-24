# Ex6 — Rasa structured half

## Your answer

The structured half is Rasa running as two separate processes on my
machine — a REST server on :5005 that owns the CALM flow, and an
action server on :5055 that owns the Python rules. My scenario in
Terminal 3 never imports Rasa. It POSTs JSON to :5005 and reads back
a list of messages. That's the whole contract.

What the POST looks like matters more than the flow YAML. The body
has a slash-command in `message` (`/confirm_booking`) so Rasa's LLM
command generator routes straight to the flow without trying to
parse natural language, and the actual booking data rides in a
`metadata.booking` dict. The custom action reads that dict, sets
slots from it with `SlotSet` events, and applies the rules — party
size over 8 → reject with `party_too_large`; deposit over £300 →
reject with `deposit_too_high`; otherwise set `validation_error` to
null and generate a SHA-1 booking reference. The flow branches on
`validation_error` and utters either `booking_confirmed` or
`booking_rejected`.

The thing that made this click for me was noticing the mock in
`structured_half.py` returns identical output to the real
`ActionValidateBooking` — same party/deposit thresholds, same
booking-reference hash. Both paths are graded, and both give the
same answer for the same input. The mock exists so students without
a Rasa Pro license can still exercise the HTTP contract. The real
path is what CI actually runs.

My `normalise_booking_payload` in `validator.py` handles the
canonicalisation upstream — `"Haymarket Tap"` → `"haymarket_tap"`,
`"7:30pm"` → `"19:30"`, `"£200"` → `200`, `"25th April 2026"` →
`"2026-04-25"`. Rasa never sees the raw human forms. Anything that
fails to normalise raises `ValidationFailed`, which the structured
half catches and returns as `next_action="escalate"` rather than
crashing.

Three design choices I'd flag: (1) the `from_llm` slot mappings in
`domain.yml` are intentionally not used on this path — slash
commands bypass them, which is why the action has to read metadata
by hand; (2) network errors are translated to
`SA_EXT_SERVICE_UNAVAILABLE` so the loop half decides what to retry;
(3) the sender ID is a hash of venue + date + time so Rasa's tracker
is consistent across retries within one session.

## Citations

- `starter/rasa_half/validator.py` — `normalise_booking_payload` +
  parse/canonicalise helpers
- `starter/rasa_half/structured_half.py` — `RasaStructuredHalf.run`
  and `_MockRasaHandler` (same rules in both)
- `rasa_project/actions/actions.py` — `ActionValidateBooking` with
  party>8 / deposit>£300 thresholds
- `rasa_project/data/flows.yml` — `confirm_booking` flow branching
  on `slots.validation_error`
