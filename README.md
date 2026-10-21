# Daily Strength

Mobile-friendly lift and food tracking with daily calorie, protein, set, and volume totals. Log workouts with individual set weights and reps in kg or lb. Device-only mode uses browser storage; signed-in mode saves food, lifts, and daily check-ins to your account on the app server.

## Run

Python 3 is required; there are no dependencies to install.

```sh
cd /workspace/elijah-risso
python3 server.py
```

The development server uses port 3002. Create an account or sign in to sync through this running server. Use the same app address on every device. Device-only logs remain separate until explicitly imported.

## Meal estimates

Upload a JPEG, PNG, or WebP meal photo under 5 MB, describe ingredients and amounts, or combine both. Analysis sends submitted content to OpenAI. Set `AI_API_KEY` securely in environment settings; never store it in the repository. The server calls OpenAI's `gpt-4.1-mini` model and keeps credentials out of the browser.

Review estimated ingredients and adjust their gram weights, then use the calculated macros in the food form and save. Estimates scale with portion weight. Photo weights, hidden oils, and nutrition are uncertain; verify them before logging. Known calories and macros can also be entered directly without AI access.

Without the key, analysis reports that configuration is required; manual food and lift logging remain available. This is a local development server; HTTPS, durable database storage, backups, email verification, password recovery, and production server hardening are still needed before public hosting.

## Food search

Search the built-in starter catalog of 36 common foods; no key or network service is needed. Search matches all entered words regardless of case. Select one or more ingredients, adjust their weights in grams in the review panel, and choose **Use these macros** before saving with **Add food**. A 200 g portion uses twice the listed per-100-g nutrition. Match the listed preparation (raw versus cooked). Catalog values are approximate references, not a comprehensive or brand-specific nutrition database; check product labels. Foods outside the catalog can be entered manually or estimated with meal analysis.

## Lifts and progress

Choose a suggested exercise or type any custom lift. Record weight and reps for each set, add/remove sets, mark warm-ups, and edit saved lifts. Specify primary and secondary muscles; suggested exercises fill them automatically. Weight is stored in kg internally, with a kg/lb entry and display selector. Use combined load for dumbbells and added load for bodyweight movements. Older equal-set logs remain readable.

Progress groups working sets by exercise name (ignoring case and extra spaces) and date. It shows heaviest set and its reps, working-set volume, and estimated one-rep max (Epley, 1–12 reps only). Warm-ups are excluded. The daily dashboard includes all recorded sets, including warm-ups.

## Muscle readiness

This is a transparent workload heuristic, not a measured recovery score. Each working set adds 12 load points to primary muscles and 6 to secondary muscles. Load decreases linearly to zero over three calendar days; recent sessions accumulate. Readiness starts at 100 and subtracts load, 15 per soreness level, and 10 per fatigue level, bounded at 0–100. A pain report overrides the status to “Avoid loading”. Scores of 75+ are “More rested”; 45–74 are “Recovering”; lower scores suggest rest. The calculation uses calendar dates, not exact hours, and does not account for actual intensity or medical recovery.

Daily check-ins record overall fatigue and muscle-specific soreness/pain. Future lifts are excluded. A muscle with no training in the last seven days and no symptoms shows “No recent data”, rather than an unsupported readiness claim. Older custom lifts need muscle mappings before they contribute.

## Development accounts

Accounts use salted scrypt password hashes, hashed session tokens, HttpOnly/SameSite cookies, per-user SQLite data, and revision checks to reject stale overwrites. Sessions last 30 days. Sign-in attempts are limited in memory. Cross-device behavior was tested using two isolated browser contexts connected to the same development server; remote phone access and deployment have not been configured.

The ignored `.data/accounts.sqlite3` holds account data. Preserve it on persistent storage and back it up for any deployment; copying source code alone does not migrate accounts. No email verification or password recovery is provided yet. Test/production accounts should not be shared through an environment template.

## Validation

```sh
node --test tests/training.test.js
python3 -m unittest discover -s tests -p 'test_*.py'
```

Browser checks also exercised individual-set entry, edits, persistence, progress, pain check-ins, mobile layout, food search, and account registration/login/sync/conflict handling.
