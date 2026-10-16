# Ticket Triage with n8n, Claude and FastAPI

A practice project: an n8n workflow that sorts incoming customer support tickets, routes them to the right team, alerts on urgent ones and logs every ticket. The team, the tickets and all test data are **invented**. No real customer data is used anywhere.

## Problem

A support team gets 100 to 200 messages a day, and one person sorts them by hand into category, urgency and responsible team. This causes four problems:

- Urgent messages wait, because there is no fast track.
- Unsure cases are sometimes routed to the wrong team and have to be re-routed.
- Sorting depends on one person, so it is a bottleneck and the result varies between people.
- Nobody has an overview, because the sorting result is not recorded anywhere.

## Solution

A workflow that reads each ticket, labels it with an AI model, checks the AI's answer, routes the ticket and records what happened. It only **sorts**. It never replies to customers and never sends anything outside the team, so a human stays responsible for every answer.

## How it works

```
Webhook (ticket arrives)
  -> Claude (category, urgency, language, summary, confidence as JSON)
  -> FastAPI service /validate (parse and validate the AI answer)
       success -> add original ticket text
                   -> Switch 1 "safety check"
                        needs_review, category "unclear" or confidence < 0.7 -> human review
                        otherwise -> Switch 2 "route by team" -> billing / technical_it / help_desk / marketing
                   -> (in parallel) urgency "high" -> alert email
       error   -> human review
  every ticket -> one row in the Google Sheet log
```

Design decisions:

- **Structured output.** The AI must return a fixed JSON object with allowed values only. A Switch node compares exact words, so free text would not be usable.
- **Validation in a separate service.** `main.py` parses the AI's text and checks it with Pydantic (allowed categories, urgency levels, languages, confidence between 0 and 1). If anything is wrong, the ticket goes to a human with `needs_review: true`.
- **Two Switch nodes.** The first only protects (is it safe to automate this ticket?). The second only routes by category.
- **The alert is a parallel branch.** It never writes to the log and never routes, so every ticket passes the safety check and gets exactly one log row.
- **Teams get the original text.** The AI's summary can lose details, so the original ticket text travels next to the AI's labels.
- **Failures are safe.** If the service is down or the AI's answer is unusable, the ticket goes to human review and is still logged.
- **The log holds no ticket text.** It stores only id, team, urgency, confidence, timestamp and category.

## Tech stack

- n8n (self-hosted in Docker)
- Claude API with a small, low-cost model, chosen to keep cost down
- FastAPI and Pydantic for the validation service
- Google Sheets for the log, Gmail for the urgent alert

## Results (measured on invented test data)

| Test | Result |
|---|---|
| First set, 20 clean messages | Category correct: 20 of 20. Urgency correct: 17 of 20, all three differences in the safe direction (the AI rated the ticket more urgent than my label). |
| Same ticket repeated 3 times | The same team every time after the category definitions were made unambiguous. |
| Harder set, 10 messages (two topics, one-word messages, angry message, mixed languages, an instruction injected into the ticket text, off-topic) | The injected instruction was ignored. Unclear tickets went to human review. The test found a design bug (see below). |
| Error path (service stopped on purpose) | The ticket still reached human review and was logged. |

Findings:

- **Bug found and fixed.** An early version let the alert branch write its own log row, so urgent tickets with low confidence skipped the safety check. The alert branch now only alerts.
- **Overlapping labels.** "Switch to a cheaper plan" fits both billing and help desk. The AI chose differently until the category definitions said who owns plan changes. Unclear business rules show up as inconsistent AI answers.
- **Run-to-run variation.** The same message can get a slightly different answer on another run, so one test run proves little.
- **Google Sheets lost rows under parallel writes.** With 1 second between requests, 3 of 5 rows were lost. With 10 seconds between requests, none were.

## Limits

- Small sample (30 messages), and I wrote the expected labels myself.
- The AI's confidence value is a rough signal, not a measured probability. The 0.7 threshold is a first guess. In the tests every ticket below 0.7 was also `unclear`, so the threshold itself has not been shown to catch a wrong answer on its own.
- Only `en` and `de` are allowed as languages. A message in another language can end up labelled as one of these and routed to a team that may not read it.
- Personal-data removal before the AI step is not built yet.
- Cost per ticket has not been measured yet.
- Google Sheets is fine for a demo but not for many simultaneous tickets. A database would be the next step.

## Setup

1. Create a virtual environment and install the packages:
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Start the validation service:
   ```
   python -m uvicorn main:app --port 8000
   ```
3. Import `Triagev1.json` into n8n and connect your own credentials (Anthropic, Google Sheets, Gmail).
4. Replace the placeholders in the workflow: `YOUR_EMAIL_HERE` (alert recipient) and `YOUR_SHEET_ID` (your log sheet).
5. Create a Google Sheet with the header row `ticket_id, team, urgency, confidence, timestamp, category`.
6. If n8n runs in Docker, the HTTP Request node must call the service at `http://host.docker.internal:8000/validate`, because `localhost` inside the container is the container itself.

Send a test ticket:

```
curl -X POST http://localhost:5678/webhook-test/triage-test \
  -H "Content-Type: application/json" \
  -d '{"id": "T-001", "text": "I was charged twice for October and my account is overdrawn. Fix this today or I will cancel.", "from": "customer-001"}'
```

## Next steps

- Remove personal data from the ticket text before it goes to the AI.
- Measure real cost per ticket from the API usage numbers.
- Replace the Google Sheet with a database.
- Add a human approval step with an AI-drafted reply (nothing sent automatically).
- Weekly summary report from the log.
