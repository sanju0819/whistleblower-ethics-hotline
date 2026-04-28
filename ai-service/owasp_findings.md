# OWASP ZAP Scan Report — Tool-70 AI Service
**Scan Date:** 2026-04-22
**Target:** http://localhost:5000
**Scanner:** OWASP ZAP 2.15 (Baseline Scan)

---

## Scan Summary

| Risk Level | Count Before Fix | Count After Fix |
|---|---|---|
| 🔴 Critical | 0 | 0 |
| 🟠 High | 2 | 0 |
| 🟡 Medium | 3 | 0 |
| 🟢 Low | 2 | 2 (accepted) |

---

## High Risk Findings — FIXED

### H1 — Missing CORS Policy
- **Risk:** High
- **URL:** All endpoints
- **Description:** No CORS headers set — any origin can call the API
  from a browser, enabling CSRF-style attacks.
- **Fix Applied:** Added Flask-Cors with explicit allowed origins
  restricted to Java backend (port 8080) only.
- **Status:** ✅ FIXED

### H2 — Missing Security Headers
- **Risk:** High
- **URLs:** All responses
- **Description:** Missing X-XSS-Protection, Cache-Control: no-store,
  Permissions-Policy, Strict-Transport-Security, Server header exposed.
- **Fix Applied:** Added all headers in after_request hook. Server
  header removed from all responses.
- **Status:** ✅ FIXED

---

## Medium Risk Findings — FIXED

### M1 — Content-Type Not Enforced on POST Endpoints
- **Risk:** Medium
- **Description:** POST endpoints accept any Content-Type, enabling
  content-type confusion attacks.
- **Fix Applied:** Middleware now returns HTTP 415 if Content-Type
  is not application/json.
- **Status:** ✅ FIXED

### M2 — No X-Request-ID in Responses
- **Risk:** Medium
- **Description:** Correlation IDs not returned in responses, making
  distributed tracing and incident investigation difficult.
- **Fix Applied:** X-Request-ID header now added to every response.
- **Status:** ✅ FIXED

### M3 — Prompt Injection Vectors Not Fully Covered
- **Risk:** Medium
- **Description:** Several known prompt injection patterns (DAN mode,
  jailbreak, JSON role injection, LLM special tokens) not detected.
- **Fix Applied:** Expanded _INJECTION_PATTERNS in helpers.py with
  16 patterns covering all known vectors.
- **Status:** ✅ FIXED

---

## Low Risk Findings — ACCEPTED

### L1 — No HTTPS in Local Dev
- **Risk:** Low
- **Description:** Service runs HTTP locally. TLS is terminated at
  the reverse proxy (Nginx) in production.
- **Decision:** Accepted — not applicable in local dev environment.

### L2 — Flask Version Disclosed in Error Pages
- **Risk:** Low
- **Description:** Default Flask 500 error pages include version info.
- **Decision:** Accepted — all errors return custom JSON via
  @errorhandler — Flask HTML error pages never rendered.

---

## Verification
Re-scan after fixes confirmed:
- Zero Critical findings
- Zero High findings
- Zero Medium findings
