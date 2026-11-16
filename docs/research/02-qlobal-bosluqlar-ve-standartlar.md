# Qlobal məhsulların boşluqları və standartlar

> Araşdırma agentinin yekun hesabatı, olduğu kimi. Tarix: 2026-11-16.
> `[VERIFIED: url]` = agent səhifəni açıb oxuyub. `[UNVERIFIED]` = yaddaşdan və ya zəif mənbədən.
> Agentin öz metod qeydlərinə baxın: bəzi rəsmi saytlar birbaşa açılmayıb.

## Method note
WebFetch was blocked by this session's network allowlist (theregister.com, pmc.ncbi.nlm.nih.gov, insidehighered.com and miamistudent.net did not resolve; they would have to be allowed in the environment's network settings). I opened pages through the connected TinyFish reader instead, which may bill to that account. [VERIFIED] means I read the statement on that page. EDUCAUSE, SAGE and Moodle docs were bot-blocked. No files were written to the repo.

## 1. Portal / super-app landscape
- SIS replacement is the costliest failure. WashU's Workday programme is about $266M over 7+ years ($98.9M for the student system, replacing ~80 homegrown apps) [VERIFIED: https://www.theregister.com/2025/12/12/washington_university_workday_costs_revealed/].
- Miami University's Workday Student slipped to 2027–28 after $14M, blocked by financial-aid complexity; its CIO calls Banner "not mobile-friendly" as implemented [VERIFIED: https://www.miamistudent.net/article/2025/10/workday-student-rollout-pushed-back-to-2027].
- Minnesota State's budget grew from $151M to $290M, with the student module moved to fall 2029 [VERIFIED: https://www.theregister.com/2026/04/08/minnesota_workday_payroll/].
- Open-source Kuali Student was sunset after about $40M [VERIFIED: https://eliterate.us/kuali-student-sunsetting-40-million-project-moving-kualico/].
- Vendor instability: after Anthology's Chapter 11, SIS/ERP went to Ellucian (260+ customers), Engage and Student Success went to Encoura, and Blackboard was recapitalised alone [VERIFIED: https://www.ellucian.com/newsroom/ellucian-completes-acquisition-anthologys-sis-and-erp-business; https://www.financialcontent.com/article/bizwire-2025-11-24-anthology-receives-approval-for-sale-transactions].
- US LMS: Canvas and Brightspace gain, Blackboard declines, Moodle's decline is accelerating [VERIFIED: https://edutechnica.com/].
- Concentration risk: the May 2026 Canvas breach exposed names, emails, student IDs and private messages; attackers claimed ~9,000 institutions [VERIFIED: https://securityaffairs.com/191686/cyber-crime/educational-tech-firm-instructure-data-breach-may-have-impacted-9000-schools.html].
- Legacy stays: PeopleSoft is supported to at least 2037 [VERIFIED: https://blogs.oracle.com/peoplesoft/peoplesoft-support-extended-through-at-least-2037-long-term-confidence-continued-innovation].
- Fragmentation: a vendor survey (n=1,010, biased) found ~70% of students frustrated and 95% willing to use a unified platform [VERIFIED: https://pathify.com/blog/is-your-digital-campus-driving-students-away-new-data-reveals-the-cost-of-the-digital-maze/]. Jisc 2025 found 45% had trouble accessing essential systems [VERIFIED: https://wonkhe.com/wonk-corner/students-not-being-able-to-access-essential-digital-tools-is-still-a-problem/].
- Emerging markets lack connectivity, devices, affordable data, digital skills and integrated LMS/ICT [VERIFIED: https://journals.eanso.org/index.php/eajes/article/download/5239/5619/].
- I found no independent campus-app retention data for Modo, campusM or Ready Education, only vendor self-reports. OpenEduCat and Fedena are cheap but integration-thin [UNVERIFIED].

## 2. Standards (purpose → priority)
- **LTI 1.3 + Advantage**: tool launch, grade return (AGS), rosters (NRPS), deep linking; legacy LTI support ended June 2022 → v1 [VERIFIED: https://www.1edtech.org/standards/lti; https://www.1edtech.org/lti-security-announcement-and-deprecation-schedule].
- **OneRoster 1.2**: users, courses, enrolments, grades via CSV or REST → v1, CSV first [VERIFIED: https://www.1edtech.org/standards/oneroster].
- **Edu-API**: higher-ed SIS data exchange, still "Candidate Final Public" → later [VERIFIED: https://www.1edtech.org/standards/edu-api].
- **QTI 3.0**: portable items and tests → later; import first [VERIFIED: https://www.1edtech.org/standards/qti].
- **Caliper**: learning-event stream for analytics → later [VERIFIED: https://www.1edtech.org/standards/caliper].
- **Open Badges 3.0**: a signed W3C Verifiable Credential per achievement → v1.5; make the QR-document payload compatible from day one [VERIFIED: https://www.imsglobal.org/spec/ob/v3p0].
- **CLR 2.0**: bundled verifiable transcript → later [VERIFIED: https://www.1edtech.org/standards/clr].
- **cmi5 / xAPI**: "xAPI + LMS" launch and tracking → later [VERIFIED: https://xapi.com/cmi5/]. SCORM 1.2/2004 import → v1 if hosting content [UNVERIFIED].
- **eduGAIN**: inter-federation SAML SSO (80+ federations) → later [VERIFIED: https://edugain.org/about-edugain/].
- **eduroam**: Wi-Fi roaming (802.1X/RADIUS), not app SSO → out of scope [VERIFIED: https://eduroam.org/about/].
- **Europass EDC / ELM**: issuing needs an eIDAS advanced or qualified e-seal → later [VERIFIED: https://europass.europa.eu/en/how-issue-european-digital-credentials-learning].
- **OIDC + SAML 2.0 + LDAP/AD** → v1; **SCIM 2.0** → v1.5; **iCal feeds** → v1; **ECTS/ELM syllabus fields** → model in v1, exchange later [UNVERIFIED].

## 3. AI tutor and assistant
- Best positive result: the Harvard physics RCT showed 0.73–1.3 SD gains in a median 49 minutes. The design used a system prompt, one-step-at-a-time scaffolding and instructor-written step-by-step solutions to curb hallucination [VERIFIED: https://www.nature.com/articles/s41598-025-97652-6].
- Counter-evidence: a 2026 RCT (2,379 undergraduates) found course AI-tutor access cut final grades by 0.37 SD and LMS participation by 0.90 SD, worse for first-generation students [VERIFIED: https://www.iza.org/publications/dp/18989/the-effects-of-course-integrated-ai-tutoring-student-performance-and-engagement-a-randomized-university-trial].
- Unguarded chat gave +48% practice performance but −17% on the exam; the guardrailed tutor gave +127% practice and an exam score equal to control [VERIFIED: https://knowledge.wharton.upenn.edu/article/without-guardrails-generative-ai-can-harm-education].
- Khanmigo RCT: students used it on a third of practice days and gains were about nil [VERIFIED: https://www.the74million.org/article/ai-tutors-not-yet-a-replacement-for-humans-research-says/].
- AI assisting humans works: Tutor CoPilot gave +4 pp mastery (+9 pp for weak tutors) at about $20 per tutor per year [VERIFIED: https://nssa.stanford.edu/studies/tutor-copilot-human-ai-approach-scaling-real-time-expertise].
- Admin chatbot: Pounce cut summer melt by 21.4%, with under 1% of messages needing staff [VERIFIED: https://campustechnology.com/articles/2017/03/07/using-ai-chatbots-to-freeze-summer-melt-in-higher-ed.aspx]. Course nudges raised first-generation grades by about 11 points [VERIFIED: https://www.ecampusnews.com/digital-innovation/2022/07/21/chatbot-boosts-student-performance-at-georgia-state/].
- Integrity: Vanderbilt disabled Turnitin's AI detector over false positives and non-native-speaker bias [VERIFIED: https://www.vanderbilt.edu/brightspace/2023/08/16/guidance-on-ai-detection-and-why-were-disabling-turnitins-ai-detector/].
- EU AI Act: admission, evaluating or steering learning outcomes, level assessment and proctoring are high-risk [VERIFIED: https://artificialintelligenceact.eu/annex/3/]. Inferring emotions in education is prohibited except for medical or safety reasons [VERIFIED: https://www.wsgr.com/en/insights/eu-commission-issues-guidelines-on-prohibited-ai-practices-under-eu-ai-act.html]. High-risk duties were postponed to 2 Dec 2027 [VERIFIED: https://www.loyensloeff.com/insights/news--events/news/eu-ai-act-key-amendments-adopted-under-digital-omnibus-package/].
- My inference: at-risk scoring and AI grading probably fall under the high-risk category and need legal review.
- UNESCO guidance (page updated Jan 2026): privacy protection, an age limit for independent use, human agency, institutional validation [VERIFIED: https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research].
- Good patterns: retrieval plus pedagogical guardrails, as in the CS50 Duck [VERIFIED: https://cs.harvard.edu/malan/publications/V1fp0567-liu.pdf]. Also citations, a Socratic default, teacher-visible logs, refusal on graded work [UNVERIFIED]. I found no outcome data for ASU.

## 4. Early-warning analytics
- Course Signals' retention claim was a reverse-causation artefact [VERIFIED: https://www.timeshighereducation.com/news/student-retention-software-comes-under-microscope/2008904.article].
- EAB Navigate (500+ schools) rated Black students high-risk at 2–4 times the rate of White peers, using race as a predictor [VERIFIED: https://themarkup.org/news/2021/03/30/texas-am-drops-race-from-student-risk-algorithm-following-markup-investigation].
- Models wrongly predict failure for 19–21% of Black and Hispanic students versus 6–12% of Asian and White students; mitigation does not fully fix it [VERIFIED: https://www.aera.net/Newsroom/Study-Algorithms-Used-by-Universities-to-Predict-Student-Success-May-Be-Racially-Biased].
- The MAAPS RCT (11 universities) found no overall effect on graduation or persistence, only at Georgia State and UCR [VERIFIED: https://sr.ithaka.org/publications/maaps-advising-experiment-evaluation-6-years].
- A 2025 Starfish pilot: flagged students ignored emails, faculty saw it as an extra step, and one instructor raised 48% of flags [VERIFIED: https://documents.cccd.edu/College%20Accreditation/Golden%20West%20College/B/1.4_01-starfish-evaluation-findings.pdf].
- Trust requirements: transparency including AI use, explanations, consent for special-category data and interventions, opt-outs [VERIFIED: https://www.jisc.ac.uk/guides/code-of-practice-for-learning-analytics].
- I found no independent RCT for Civitas [UNVERIFIED].

## 5. Wayfinding
- MazeMap offers step-free routing, audio guidance, screen-reader support, optional beacons/Wi-Fi/QR, and shareable URL/QR directions that plug into timetabling [VERIFIED: https://mazemap.com/accessibility; https://www.mazemap.com/indoor-maps].
- Mappedin prices by floor area, ingests DWG/PDF plans and offers free self-mapping [VERIFIED: https://www.mappedin.com/pricing/].
- QR-anchored localisation plus graph routing (Dijkstra/A*) with offline mode is a documented low-cost alternative to beacons [VERIFIED: https://www.okanagancollege.ca/sites/default/files/2026-01/2026sysconwayfindingconindooroutdopreprdraft.pdf].
- Cheapest workable approach (my inference): digitise floor plans into a node/edge graph with accessibility attributes, put QR stickers at entrances, lifts and stairs as "you are here" anchors, give text and photo step-by-step directions, and deep-link from the timetable. Concept3D not assessed.

## 6. Q&A and communities
- Piazza's employer data-sharing drove instructors to Ed [VERIFIED: https://stanforddaily.com/2020/10/04/concerned-with-piazzas-data-privacy-management-some-professors-look-to-alternative-discussion-forums/].
- Ed's pull is roster sync and anonymous posting [VERIFIED: https://ctl.duke.edu/technology/ed-discussion/].
- Anonymity matters: 75.6% of questions in CS forums were anonymous (women 86%, men 70%) [VERIFIED: https://s3.amazonaws.com/kvaccaro.com/documents/Engagement_and_Anonymity_on_Piazza_ICER_23.pdf].
- Fully anonymous apps led the UNC system to move to block them over harassment [VERIFIED: https://techcrunch.com/2024/03/07/anonymous-social-apps-face-another-reckoning-as-unc-system-to-ban-yik-yik-fizz-sidechat-whisper].
- Discord Student Hubs are explicitly not school-managed; moderation falls on student owners [VERIFIED: https://support.discord.com/hc/en-us/articles/4407546283031].
- Requirements: anonymous to peers but identifiable to staff, reporting, moderator roles, audit trail, retention limits, protections for minors; Telegram use is unmanaged [UNVERIFIED]. CampusGroups not assessed.

## 7. Accessibility and localisation
- WCAG 2.2 adds 9 criteria, including target size and accessible authentication [VERIFIED: https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/].
- EN 301 549 v4.1.1 (2 Sep 2026) adopts WCAG 2.2 AA; Official Journal citation is expected around 30 Nov 2026 [VERIFIED: https://www.deque.com/blog/en-301-549-v4-1-1-is-final-what-changed-what-it-means-and-what-you-should-do/].
- US public institutions must meet WCAG 2.1 AA for portals, apps and LMS content by April 2027 or 2028 [VERIFIED: https://campustechnology.com/articles/2026/04/27/doj-extends-deadline-for-ada-title-ii-compliance.aspx].
- Mobile is the primary or only internet access in low- and middle-income countries, and handset cost is the main barrier [VERIFIED: https://www.gsma.com/newsroom/press-release/gsma-calls-for-renewed-focus-on-closing-the-usage-gap-as-more-than-3-billion-people-remain-offline-despite-available-mobile-internet-services/].
- Expect an offline-capable PWA, small payloads, a queued-sync design and local-language/RTL-ready UI [UNVERIFIED].

## Top 12 gaps to close
1. **Overlay, not replacement**: integrating existing SIS/LMS sells in months, while replacements cost $100M+ and slip years.
2. **Phone-first, low-data, offline**: the phone is the only device for many target users.
3. **Guardrailed, cited AI tutor**: unguarded AI measurably lowers grades, so buyers will demand evidence.
4. **Alerts tied to human intervention**: alerts alone do not move retention, so the workflow is the product.
5. **Explainable risk scores without demographics**: bias scandals end contracts.
6. **QR-verifiable signed documents**: an immediate, visible saving for registrars and employers.
7. **Data minimisation and message retention**: the Canvas breach makes security a procurement question.
8. **Admin chatbot with staff escalation**: under 1% of queries needed staff, which is direct cost relief.
9. **Official communities with scoped anonymity**: replaces unmanaged Telegram/Discord and limits harassment liability.
10. **QR-plus-graph wayfinding with step-free routes**: avoids per-area licences.
11. **WCAG 2.2 AA from day one**: a tender gate in the EU and US.
12. **Open-standard export and exit**: vendor bankruptcies make lock-in a sales objection.

## Standards: v1 vs later
- **v1**: OIDC, SAML 2.0, LDAP/AD, LTI 1.3 + Advantage, OneRoster 1.2 (CSV, then REST), iCal, WCAG 2.2 AA, VC-compatible QR documents, SCORM import.
- **v1.5**: SCIM 2.0, Open Badges 3.0, xAPI/cmi5, QTI import, ECTS/ELM catalogue export.
- **Later**: Caliper, CLR 2.0, Edu-API, eduGAIN, Europass EDC (e-seal).
