# NIST və uyğunluq xəritəsi

> Araşdırma agentinin yekun hesabatı, olduğu kimi. Tarix: 2026-11-16.
> `[VERIFIED: url]` = agent səhifəni açıb oxuyub. `[UNVERIFIED]` = yaddaşdan və ya zəif mənbədən.
> Agentin öz metod qeydlərinə baxın: bəzi rəsmi saytlar birbaşa açılmayıb.

**Method note.** Direct fetches of nist.gov, csrc.nist.gov and owasp.org were blocked by this session's network policy (those hosts must be allowed in the session's network settings). So [VERIFIED: url] means "confirmed through web-search extracts of that primary page", not a full page read. The control-ID and ASVS mappings in section 4 are my own, from memory of the catalogues.

**Main deltas from the brief:** SP 800-53 is at Release 5.2.0; SP 800-63-4 is final; SSDF v1.2 and Privacy Framework 1.1 are still drafts; the OWASP LLM Top 10 has a 2026 edition; ISO/IEC 27017 is now :2026 and 27701 is :2025; DigComp 3.0 replaced 2.2; NICE Components are at v2.2.0.

## 1. NIST publications

- **CSF 2.0** — final, 26 Feb 2024, still current. A CSF 2.0 to SP 800-53 r5.2.0 mapping was posted final on 17 Nov 2025. Use it as the top-level structure buyers recognise. [VERIFIED: csrc.nist.gov/pubs/cswp/29/the-nist-cybersecurity-framework-csf-20/final; nist.gov/cyberframework/informative-references]
- **SP 800-53 Rev. 5** — latest is Release 5.2.0, 27 Aug 2025 (adds SA-15(13), SA-24, SI-02(07); revises SI-07(12)). The 800-53B baselines are unchanged. This is the catalogue to cite; target a tailored Moderate baseline. [VERIFIED: csrc.nist.gov/pubs/sp/800/53/r5/upd1/final] No 5.3.0 or Rev. 6 found. [UNVERIFIED]
- **SP 800-63-4** — final, 31 Jul 2025 (63, 63A, 63B, 63C); supersedes 63-3. [VERIFIED: csrc.nist.gov/pubs/sp/800/63/4/final] Key requirements [VERIFIED: pages.nist.gov/800-63-4/sp800-63b.html; pages.nist.gov/800-63-4/sp800-63c/fal/]:
  - **Passwords:** at least 15 characters as sole factor, 8 inside MFA; allow 64 or more; blocklist check; no composition rules; no periodic change; salted (32 bits or more) hash.
  - **Sessions:** AAL1 reauthentication within 30 days; AAL2 within 24 h overall and 1 h idle, with a phishing-resistant option available; AAL3 within 12 h and 15 min idle, phishing-resistant required.
  - **Federation:** FAL1 is a signed, audience-restricted assertion; FAL2 adds single-relying-party audience, injection protection and a pre-agreed trust agreement; FAL3 adds proof of a subscriber-held authenticator.
  - **My recommendation:** students at AAL1 minimum, with AAL2 for exams and official documents; staff and admins at AAL2 with passkeys; the university does identity proofing and the product federates (SAML/OIDC) at FAL2.
- **SP 800-171 Rev. 3** — final, May 2024. US universities meet it through federal research contracts carrying controlled unclassified information and Federal Student Aid expectations. Outside the US it is not mandatory; it is useful as a confidentiality subset of the Moderate baseline. [VERIFIED: csrc.nist.gov/pubs/sp/800/171/r3/final; fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2020-12-18/protecting-student-information-compliance-cui-and-glba] DoD contracts still require Rev. 2. [UNVERIFIED]
- **SP 800-218 (SSDF)** — v1.1 (Feb 2022) remains final. Rev. 1 (v1.2) was drafted 17 Dec 2025 and was still a draft in NIST's May 2026 material. SP 800-218A (generative-AI profile) is final, 26 Jul 2024. [VERIFIED: csrc.nist.gov/pubs/sp/800/218/r1/ipd; csrc.nist.gov/projects/ssdf/publications] Status after May 2026. [UNVERIFIED]
- **AI documents** — AI RMF 1.0 is "being revised", with no replacement text found; the Generative AI Profile (AI 600-1, Jul 2024) is still listed. The Cyber AI Profile (IR 8596) exists only as a preliminary draft, 16 Dec 2025. The SP 800-53 AI control overlays have nothing final. [VERIFIED: nist.gov/itl/ai-risk-management-framework; csrc.nist.gov/pubs/ir/8596/iprd]
  - NIST's project page reports the overlays were renamed "Control Overlays for Super Intelligence Systems" on 20 Oct 2026, after a 29 Sep 2026 executive order replacing "AI" with "Super Intelligence" in federal usage. Expect NIST AI titles to change. [VERIFIED: csrc.nist.gov/projects/cosis]
- **Privacy Framework** — 1.0 is still the final version. The 1.1 draft is dated 14 Apr 2025; the final was promised for 2026 and not found. [VERIFIED: nist.gov/privacy-framework/new-projects/privacy-framework-version-11]
- **SP 800-61 Rev. 3** — final, 3 Apr 2025; an incident-response profile of CSF 2.0. [VERIFIED: csrc.nist.gov/projects/incident-response]
- **SP 800-92** — the 2006 original is still final; the Rev. 1 draft (Oct 2023) is not finalised. [VERIFIED: csrc.nist.gov/pubs/sp/800/92/r1/ipd]
- **SP 800-34 Rev. 1** — 2010; no Rev. 2 found. [VERIFIED: nist.gov/privacy-framework/nist-sp-800-34]
- **SP 800-207** — final 2020; implementation guide SP 1800-35 final June 2025. Principle: authenticate and authorise every request. [VERIFIED: csrc.nist.gov/pubs/sp/1800/35/final]
- **FIPS 140-3** — FIPS 140-2 certificates moved to the Historical list on 21–22 Sep 2026, so new procurements need 140-3 modules. [VERIFIED: csrc.nist.gov/projects/cryptographic-module-validation-program]
- **Password hashing** — PBKDF2 (SP 800-132, 2010) is the only NIST-approved password scheme. NIST announced in 2023 it would add a memory-hard function; no draft found. [VERIFIED: nist.gov/news-events/news/2023/05/nist-revise-sp-800-132-recommendation-password-based-key-derivation-part-1]
  - 800-63B-4 says an approved scheme "SHOULD" be used, so Argon2id (OWASP's first choice, at least 19 MiB and 2 iterations) is defensible. Use PBKDF2-HMAC-SHA-256 where a buyer demands FIPS-approved algorithms. [VERIFIED: cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html]

## 2. NICE and syllabus frameworks

- **Status:** SP 800-181 Rev. 1 is final. [VERIFIED: csrc.nist.gov/pubs/sp/800/181/r1/final] The content lives in NICE Framework Components, currently v2.2.0 (28 Apr 2026; NIST's page prints "2025"), which adds a supply-chain risk management work role. [VERIFIED: nist.gov/itl/applied-cybersecurity/nice/nice-framework-resource-center/nice-framework-current-versions]
- **How universities map:** pick target Work Roles or Competency Areas per programme, then tag each course outcome with Knowledge and Skill statement IDs (Tasks for labs and capstones), and report coverage per Work Role. [VERIFIED: nist.gov/itl/applied-cybersecurity/nice/nice-framework-resource-center/about/faq/k12-faq]
- **Machine-readable data:** XLSX and JSON in NIST's CPRT schema (not OSCAL), plus CTDL via the Credential Registry. Store the statement ID and the components version. [VERIFIED: nist.gov/itl/applied-cybersecurity/nice/nice-framework-resource-center/faq-nice-framework-data-json-format]
- **Generic container:** 1EdTech CASE 1.1 (final 24 Jan 2025) is a REST/JSON standard for outcome frameworks and associations; a good internal model for everything below. [VERIFIED: 1edtech.org/standards/case]

One line each for a syllabus builder:
- **ECTS (Users' Guide 2015):** verifiable outcomes plus workload per course; 1 credit is 25–30 h. [VERIFIED: education.ec.europa.eu/sites/default/files/document-library-docs/ects-users-guide_en.pdf]
- **EQF:** level tag per programme or course (6 bachelor, 7 master, 8 doctorate). [VERIFIED: eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017H0615(01)]
- **ESCO v1.2.1 (Dec 2025):** tag outcomes with skill URIs; CSV, JSON-LD and API available. [VERIFIED: esco.ec.europa.eu/en/use-esco/download]
- **CS2023:** coverage check against 17 knowledge areas and core hours. [VERIFIED: csed.acm.org]
- **ABET:** course-to-student-outcome (1–5) matrix; 2026–27 criteria. [VERIFIED: abet.org/accreditation/accreditation-criteria/criteria-for-accrediting-computing-programs-2026-2027/]
- **Bloom's (revised):** cognitive-level verb per outcome; align assessments. [UNVERIFIED]
- **e-CF (EN 16234-1:2019):** ICT-professional competences with proficiency levels; 2019 appears current. [UNVERIFIED]
- **DigComp:** 3.0 (27 Nov 2025) supersedes 2.2; transversal digital and AI competence tags for any faculty. [VERIFIED: joint-research-centre.ec.europa.eu/jrc-news-and-updates/european-commission-updates-its-digital-competence-framework-digcomp-2025-11-27_en]
- **SFIA 9 (Oct 2024; SFIA 10 planned Q4 2027):** skill plus responsibility-level tags; JSON and RDF downloads. [VERIFIED: sfia-online.org/en/sfia-10]

## 3. Non-NIST companions

- **ISO/IEC 27001:2022 + Amd 1:2024** — the certifiable security management system. [VERIFIED: iso.org/standard/27001]
- **ISO/IEC 27701:2025** — edition 2, Oct 2025; privacy management. [VERIFIED: iso.org/standard/27701]
- **ISO/IEC 27017:2026** (edition 2, Jul 2026) and **27018:2025** — cloud and cloud personal-data guidance. [VERIFIED: iso.org/standard/27017; iso.org/standard/27018]
- **ISO/IEC 42001:2023** — certifiable AI management system. [VERIFIED: iso.org/standard/42001]
- **SOC 2** — 2017 Trust Services Criteria with 2022 points of focus. AICPA proposed an update on 28 Oct 2026 adding AI governance; not final. [VERIFIED: aicpa-cima.com/news/article/aicpa-proposes-update-of-soc-2-r-trust-services-criteria-to-enhance-the-relevance-usability-and-value-of-cpas-reports]
- **OWASP ASVS 5.0.0** — stable, 17 chapters. [VERIFIED: asvs.owasp.org] Release date 30 May 2025. [UNVERIFIED]
- **OWASP Top 10:2025** — current; new A03 Software Supply Chain Failures and A10 Mishandling of Exceptional Conditions. [VERIFIED: owasp.org/Top10/2025/]
- **OWASP LLM Top 10** — a 2026 edition (about 2 Sep 2026) supersedes 2025. I could not retrieve its category list. [VERIFIED: genai.owasp.org/resource/owasp-genai-llm-top-10-2026/]
- **OWASP API Security Top 10** — 2023 is still the latest. [VERIFIED: owasp.org/API-Security/]
- **CIS Controls v8.1** — 24 Jun 2024; v9 in development. [VERIFIED: cisecurity.org/controls]
- **1EdTech TrustEd Apps** — Data Privacy Rubric (1EdTech vets public policies and awards a seal), Security Practices Rubric, Generative AI Data Rubric (self-assessment). [VERIFIED: 1edtech.org/program/trustedapps]
- **HECVAT 4** — current version 4.1.6; one workbook with AI and privacy sections; free for vendors; update yearly. [VERIFIED: educause.edu/higher-education-community-vendor-assessment-toolkit]

## 4. Minimum credible control set

Priority tags: D1–3 = before any real student data; D30; D90. "—" = no ASVS chapter applies.

| # | Control | SP 800-53 r5 | ASVS 5.0 | When |
|---|---|---|---|---|
| | **GOVERN** | | | |
| 1 | Named security/privacy owner, policies, risk register, security plan | PM-2, PL-2, RA-3, CA-5 | — | D30 |
| 2 | Data inventory, retention schedule, consent records, data-processing agreement per university | PM-5(1), PT-2, PT-4, SI-12 | V14 | D1–3 |
| 3 | LLM-provider and sub-processor agreements (no training on data, region, retention) | SA-9, SR-3, SR-6 | — | D1–3 |
| 4 | AI policy: no personal data to external LLM without agreement; output labelled AI; humans decide grades | PT-3, AC-4, SA-9 | V14 | D1–3 |
| 5 | Secure development: reviewed merges, threat model, release checklist | SA-3, SA-8, SA-11, CM-3 | V15 | D30 |
| | **IDENTIFY** | | | |
| 6 | Asset and dependency inventory (SBOM) | CM-8, SR-4 | V15 | D30 |
| 7 | Dependency, secret and static scanning in CI | RA-5, SA-11, SI-2 | V15 | D1–3 |
| 8 | Patch deadlines; annual external penetration test against ASVS Level 2 | SI-2, CA-8 | all | D90 |
| 9 | Privacy impact assessment for grades, exams, AI tutor | RA-8, RA-3 | — | D30 |
| | **PROTECT** | | | |
| 10 | Real authentication: SSO or 800-63B passwords, salted Argon2id/PBKDF2 hashes | IA-2, IA-5(1), IA-8 | V6, V10, V11 | D1–3 |
| 11 | MFA for staff/admin, passkey option | IA-2(1), IA-2(2) | V6 | D1–3 |
| 12 | Server-side role checks plus object-level authorisation on every endpoint, deny by default | AC-3, AC-3(7), AC-6 | V8, V4 | D1–3 |
| 13 | TLS everywhere, HSTS; encrypted database volume | SC-8, SC-13, SC-28 | V12, V11 | D1–3 |
| 14 | Secure session cookies, timeouts, revocation, CSRF protection | SC-23, AC-12 | V7, V3 | D1–3 |
| 15 | Input validation, parameterised SQL, output encoding, CSP | SI-10, SI-15 | V1, V2, V3 | D1–3 |
| 16 | Rate limiting, login throttling/lockout | AC-7, SC-5 | V6, V2 | D1–3 |
| 17 | Secrets out of the repo; secret store; rotate anything ever committed | IA-5(7), SC-12 | V13 | D1–3 |
| 18 | LLM safeguards: uploaded documents and model output untrusted; model has no data or tool authority; per-user quotas | SI-10, SI-15, AC-6 | V1, V2 | D1–3 |
| 19 | Safe uploads and official-document integrity (type/size checks, malware scan, signed downloads) | SI-3, SI-7, AC-3 | V5 | D30 |
| 20 | Hardened configuration: no debug, security headers, least-privilege service account, no real data in test | CM-6, CM-7, SC-7 | V13, V3 | D30 |
| 21 | Tenant isolation between universities; replace or harden single-file SQLite | AC-4, SC-4 | V8, V14 | D30 |
| 22 | Exam integrity: server-side timing, answer keys never sent to the client, tamper-evident submissions | SI-7, AU-10 | V2, V8 | D30 |
| 23 | Staff on/offboarding, access reviews, security training | AC-2, PS-4, AT-2 | — | D90 |
| | **DETECT** | | | |
| 24 | Audit log of logins, failures, role/grade changes, exports, admin actions; protected, no secrets | AU-2, AU-3, AU-9, AU-12 | V16 | D1–3 |
| 25 | Central log retention and alerts (brute force, mass export, privilege change) | AU-6, AU-11, SI-4 | V16 | D30 |
| 26 | Vulnerability-disclosure contact (security.txt) | RA-5(11) | — | D30 |
| | **RESPOND** | | | |
| 27 | Incident-response plan, contacts, breach-notification deadlines | IR-4, IR-6, IR-8 | — | D30 |
| 28 | Tabletop exercise and lessons-learned loop | IR-2, IR-3 | — | D90 |
| | **RECOVER** | | | |
| 29 | Encrypted automated off-site backups with a tested restore | CP-9, CP-9(1), CP-9(8), CP-10 | — | D1–3 |
| 30 | Contingency plan (recovery targets, exam-period continuity); data return and deletion at contract end | CP-2, CP-4, SI-12(3), MP-6 | V14 | D90 |

## 5. Honest claims

**Legitimate, if true and dated:**
- "Security programme aligned with / mapped to NIST CSF 2.0 (self-assessed)."
- "Controls mapped to the SP 800-53 Rev. 5 moderate baseline (self-assessed)."
- "Authentication designed to SP 800-63B-4 AAL2 for staff."
- "Development follows SSDF v1.1 practices."
- "Tested against OWASP ASVS 5.0 Level N by [named tester]."
- "HECVAT 4.1.x self-assessment available."
- "Uses NIST-approved algorithms."
- "Syllabus outcomes mapped to NICE Framework Components v2.2.0."

**Must not be claimed without the external process:**
- "NIST certified / approved / compliant." NIST offers no certification or endorsement and plans no conformity programme. [VERIFIED: nist.gov/cyberframework/faqs]
- "ISO 27001 / 27701 / 42001 certified" needs an accredited certification-body audit. [UNVERIFIED]
- "SOC 2 certified" does not exist; it is a CPA attestation report, so say "SOC 2 Type I/II report available" only once issued. [UNVERIFIED]
- "FedRAMP authorized / ready" needs the FedRAMP process. [UNVERIFIED]
- "FIPS 140-3 validated" applies only to a specific module with a certificate, never to the whole product. [VERIFIED: nist.gov/standardsgov/compliance-faqs-nist-it-security-validation-program]
- "HECVAT certified", "OWASP certified", "FERPA/GDPR certified", "NICE accredited": none of these exist. [UNVERIFIED]
- "1EdTech certified" only after 1EdTech vetting awards the seal. [VERIFIED: 1edtech.org/certification/data-privacy]

No files were written.
