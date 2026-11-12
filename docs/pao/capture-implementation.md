# WP5 capture and student navigation

Implemented title-first capture with optional course/topic/assessment, priority, timing and description in native HTML details. Academic selects carry exact IDs; topic/assessment ownership and active course state are checked inside the repository create transaction. Unlinked capture remains valid. Catalogue queries expose labels, identities and recorded dates only, without scoring or answer data.

Preferred day accepts ISO date, weekday or none/empty. Old invalid stored values display “Needs timing review” without modifying the row. Status filters include all/open/completed/archived, course and priority. Each task has an anchor deep link, current lifecycle label, legal transitions supplied by the service, and archived tasks have no edit or transition controls. Skipped tasks cannot show Complete. Forms retain filter context and creation errors retain entered values with details expanded.

Today, This Week, Backlog and Exams use existing planning/calendar owners and URLs. Month import is a secondary disclosure. Exams show only recorded assessment dates or Date unknown; no readiness inference. Catalogue assessment types exposed under Exams are exam, midterm, final, test and quiz.

Execution integration: activated forms carry revision and command UUID; partial progress carries an explicit occurrence instant, session minutes and optional note. These fields render only when PAO_V3_ENABLED and task.revision exist. Global planning command guard token remains on every write form.

## Integration ownership

Parent owns routes and shared service/repository commits. Route capture forwards course_id/topic_id/assessment_id. Failure rendering uses form_values (or request.form fallback); redirects retain filter_status/filter_priority/filter_course_id and task anchor. Parent provides pao_command_id(), pao_now(), revision-aware execution endpoints and preferred-day update validation. Capture repository/service changes are left unstaged for the parent to include with other shared edits.

## Verification

RED: nine capture tests failed for absent catalogue, cross-course acceptance, unconstrained timing and missing all-status handling; then passed after implementation. Final capture plus existing task tests: 20 passed. Capture tests cover exact course visibility including unlinked work, cross-course/missing/deleted/inactive rejection, preferred day date/weekday/none and invalid values, legacy timing review, skipped/archived actions, history labels/deep links and error preservation.

A combined subset with planning analysis and study actions initially passed 40/40. A later run after six more capture cases and concurrent changes passed 46 with one unrelated study-action preview failure (missing title form).

Browser validation attempted with Playwright: installed bundled Chromium executable missing; system Chromium failed to launch because socket creation was denied. Phone keyboard, expanded details, long-title layout and back navigation therefore remain unverified in a running browser. Responsive capture CSS uses a single column below 640px, wraps long task text, and highlights task anchors.
