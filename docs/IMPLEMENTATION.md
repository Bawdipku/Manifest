# PRD 1.6 implementation and validation

## Implemented

- Persistent SQLite records and private evidence, with authenticated server endpoints; session cookies, CSRF tokens, login throttling, role templates, active accounts, and branch scopes.
- Branch/city/employee/customer/fleet/rate/product/unit/vendor masters; customer and fleet selection; sender and issued invoice snapshots.
- Draft, registered, and cancelled sales; unique branch/date BKC numbers; cancellation reasons and history; five dynamic BKC copies with Code 128, all four monetary components, sender declaration, and the supplied terms on the sending branch copy.
- P2P transit/final and P2D trips; internal/vendor execution, vendor handover, retained manifests, keyboard scanner selection, up to 200 unique receipts per addition, draft removal reasons, and chronological event checks.
- Individual branch receipt, final POD, protected evidence downloads, assisted field reporting, partner assignment, administrator approval/rejection, and 24/48/72-hour follow-up views.
- SOA trip/DEST grouping, confirmed snapshots and versions, provisional policy approval, actual SOA after POD, discrepancy resolution, and revision history.
- Separate physical POD return batches and confirmation by the origin branch.
- Credit invoices before or after POD, exclusive active claims, issued snapshots, partial/full payments, duplicate reference and overpayment rejection, payment reversals, printing, and Excel exports.
- Jakarta-date reports for sales, departure, reconciliation, cancellation, invoice settlement, and documents; printing, Excel, and dated report snapshots. Invoice settlement rows are separate from sales revenue and never added as new revenue.
- Every command runs inside a SQLite transaction with a global expected revision and actor-scoped idempotency key. Global revision conflicts require a fresh view, even when two users changed different records. This favors correctness at the cost of occasional retries.
- Audit entries retain actor, time, command, and entity before/after snapshots. Transit-only access does not expose financial fields. Assignment changes take effect for every subsequent evidence and shipment request.

## Acceptance checks

`tests/test_acceptance.py` exercises the actual authenticated HTTP API and database, including:

1. Three-stage origin → hub → destination → recipient workflow; partial receipt; immutable first departure and SOA; retained old manifests; sender and invoice snapshots; financial totals and BKC generation.
2. Duplicate active trip rejection, chronology checks, vendor handover, invoice exclusive claim, overpayment and duplicate reference rejection, payment reversal, reconciliation, and physical return.
3. Partner reassignment revokes old shipment/history/evidence access, transit finance cannot see money, read-only roles cannot mutate, and transit POD approval fails.
4. Idempotent retry, stale revision rejection, CSRF enforcement, atomic rollback, anonymous denial, and the 200-receipt limit.
5. Provisional policy blocks finalization; cancellations leave history and leave active totals.
6. Partner POD approval requires evidence and admin role; it does not create SOA or return the document. Wrong branches cannot receive returns. Account disablement revokes sessions.
7. A pending field report blocks forwarding; resolution and draft removal restore operational state.

A local Chromium check also exercised login, shipment registration, customer autofill, manifest loading, SOA confirmation, navigation across all modules, and mobile layout at 390 px. It reported no JavaScript errors or page overflow. The Docker image was built and run as UID 10001; health, database integrity, and persistence across a container restart were verified. The online backup helper also passed an automated integrity check. This is not a real-device or full field-operating certification.

## Operational assumptions and limits

- Sales revenue currently equals cash + credit + destination collection. Forwarding fees are tracked separately as an expense, as confirmed by the user.
- The full app has not yet been deployed: the user will provide server hosting access. GitHub Pages still serves the earlier prototype and does not share records with this backend.
- No production data is seeded. Automated tests use clearly fictional data in temporary databases.
- Event times are captured as timezone-aware timestamps; the UI labels entry as WIB. Reports use Asia/Jakarta boundaries. The server clock must be synchronized.
- Large-scale load, real mobile/scanner/print testing, and a full recovery drill remain operational rollout gates. SQLite stores the entire current business state in one transactional document plus separate users, sessions, evidence, audit, and idempotency tables. Large deployments should move to a normalized database before scaling horizontally.
- PRD exclusions remain excluded: splitting koli among vehicles, warehouse stock balances, per-leg/vendor costing, automatic volumetric tariffs, automatic WhatsApp/notifications, offline record synchronization, public tracking, camera scanning, QR/vouchers/blanks, forecasting, and a help center.
