# Contributing to AWS Resource Lifecycle Tracker

Thank you for your interest in contributing. Please read this carefully before submitting a PR.

---

## Security Rules — Non-Negotiable

### Never commit credentials
- `.env` is in `.gitignore` — never force-add it
- `.env.example` contains only fake placeholder values — never real ones
- If you accidentally commit a real key, rotate it immediately and rewrite git history

### SQL — parameterized queries only
- Never build SQL with f-strings, `.format()`, or string concatenation
- Every query must use `%s` placeholders with a params tuple
- This rule has no exceptions — SQL injection prevention is mandatory

### XSS — no `| safe` filter in templates
- Never use Jinja2's `| safe` filter on any data that comes from AWS
- AWS tag values are user-controlled strings and must always be auto-escaped

### No debug mode in production
- `FLASK_DEBUG` must never be `true` in a deployed environment
- The app defaults to `false` — do not change this default

---

## Local Development Setup
```bash
git clone https://github.com/ADITYANAIR01/aws-resource-lifecycle-tracker
cd aws-resource-lifecycle-tracker
cp .env.example .env
# Edit .env — fill in your real values (never commit this file)
docker compose up --build
```

The poller makes real boto3 calls to your AWS account using your local credentials.
The IAM policy is read-only — the poller cannot modify or delete anything.

For hot reload during development:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

---

## Code Style

- Python 3.11
- Use `get_logger(__name__)` from `utils/logger.py` — never `print()` in production code
- Parameterized queries only — no string-built SQL anywhere
- Keep functions small and focused

---

## Adding a New Resource Type

1. Create `poller/collectors/<resource_type>.py` following the pattern in `base.py`
2. Register the collector in `poller/main.py`
3. Add alert rules in `poller/alerts/rules.py` if applicable
4. Update the dashboard resource type filter in `app/routes/resources.py`
5. Add the resource type to the README tracked resources table
6. Add cost estimation logic in `poller/utils/cost.py` if applicable

---

## Submitting a PR

- One PR per change — keep PRs small and focused
- Make sure `docker compose up --build` works cleanly before submitting
- Make sure no real credentials appear anywhere in the diff