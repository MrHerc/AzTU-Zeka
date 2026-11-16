# Azərbaycan: mövcud sistemlər, qanun, satınalma, AzTU faktları

> Araşdırma agentinin yekun hesabatı, olduğu kimi. Tarix: 2026-11-16.
> `[VERIFIED: url]` = agent səhifəni açıb oxuyub. `[UNVERIFIED]` = yaddaşdan və ya zəif mənbədən.
> Agentin öz metod qeydlərinə baxın: bəzi rəsmi saytlar birbaşa açılmayıb.

## Research report: selling a campus portal to Azerbaijani universities (16 Nov 2026)

**Method limits.** The built-in page fetcher could not reach any external host (session network allowlist), so pages were read through the TinyFish connector (metered on the connected account: roughly 25 fetch calls and 25 searches). edu.gov.az, dspace.asoiu.edu.az and metro.gov.az were unreachable; two mincom.gov.az PDFs and one ascca.gov.az PDF returned no text. Long laws and accreditation reports were keyword-extracted, not read end to end. "UNVERIFIED (snippet)" means seen only in a search-result snippet.

### 1. Existing systems
- **AzTU:** the LMS was "built with KOICA support"; login is sso.aztu.edu.az. Separate library, alumni, appeals, e-grant and majors portals exist. [VERIFIED: https://www.aztu.edu.az/az/telebeler/tedris-teqvimi-ve-qaydalar/lms-telimatlari ; https://www.aztu.edu.az/az/mexfilik-siyaseti]
- **AzTU's KOICA project:** 2011–2014, USD 2 million, covering Academic, Portal, Groupware and e-Learning modules. [VERIFIED: https://en.apa.az/social/xeber_post-project_evaluation_of_the_project_____-223047]
- **TKTA's 2023 findings on AzTU:** the KOICA system is the main information system (cabinets, attendance, announcements). TKTA said coverage should extend to e-document flow, timetables, e-journals and appeals, and that the documents shown did not cover the system's legal basis. The vice-rector for digitalisation announced a "University Management System (UMS)". Side systems are AMAS, DrSys and a library registry. [VERIFIED: https://tkta.edu.az/files/Akkreditasiya%20hesabatlar%C4%B1/AzTU_Yekun%20Hesabat_TKTA_sayt.pdf]
- **Microsoft programme:** the ministry is centrally supplying licensed Microsoft tools, including Copilot, to 20 universities. It is already live at AzTU, UNEC, ADNSU, ADPU, ATU and five others. [VERIFIED: https://operativmedia.az/post/130427/elm-ve-tehsil-nazirliyi-ve-microsoft-ali-tehsil-muessiselerinde-reqemsal-aletlere-cixisi-genislendirir]
- **AzTU website assistant:** aztu.edu.az already runs an AI chat assistant that sends messages to OpenAI gpt-4o, on a consent basis. [VERIFIED: https://www.aztu.edu.az/az/mexfilik-siyaseti]
- **UNEC:** EDUMAN e-university, student and teacher cabinets, and the myUNEC app (Face ID/PIN, offline). Its "Bir Pəncərə" service has issued signed, sealed, QR-coded PDF certificates since 2019. [VERIFIED: https://unec.edu.az/az/reqemsal-unec]
- **EduMan vendor:** built by the company Ultra; also at the Languages University and five colleges. [VERIFIED: https://xeberler.az/new/details/daha-bir-universitetde-tehsil-prosesi-elektronlasdirilir--12198.htm] Use at Ganja State and the Culture and Arts University is [UNVERIFIED (snippet)].
- **ADNSU:** Unibook from Neuron (contract dated 05.01.2017, lms.adnsu.az), Microsoft 365/Teams, and the state e-document portal esd.e-gov.az. [VERIFIED: https://asoiu.edu.az/upload/official_documents/f5bb8d4164d3612cb3072ecb9a975ea3.pdf] It has a ten-person e-education and monitoring department that also coordinates proctoring. [VERIFIED: https://asoiu.edu.az/electronic_education_and_monitoring]
- **Unibook:** cloud-based, about 50 modules, "many leading universities". [VERIFIED: https://www.trend.az/business/it/2892149.html]
- **BDU:** Blackboard Learn, Collaborate and Ally since 2021, with an Azerbaijani interface. [VERIFIED: https://bdu.info.az/en/education/education-at-bsu] A separate lms.bsu.edu.az cabinet is [UNVERIFIED (snippet)].
- **ADA:** Ellucian Banner, Blackboard and OCLC, all in the cloud. [VERIFIED: https://adawdc.org/en/view/5/5/the_firstever_digital_university_in_azerbaijan]
- **ADPU:** my.adpu.edu.az runs "Empro | Education Platform". [VERIFIED: https://my.adpu.edu.az]
- **Baku Engineering University:** uses Google Classroom and has no online-education system. Its LMS budget was 163–1,370 AZN a year, against total spending of 9–17 million AZN. [VERIFIED: https://tkta.edu.az/files/Akkreditasiya%20hesabatlar%C4%B1/BMU%20Yekun%20Hesabat_.pdf]
- **Azerbaijan University:** "Electronic University" by Cybernet (2017). [VERIFIED: https://au.edu.az/en/news/azerbaycan-universiteti-elektron-universitetin-tetbiqine-baslayir]
- **BHOS, Khazar, ATU:** in-house LMS, Moodle and "Kodera LMS" respectively. [UNVERIFIED (snippets)]
- **Not found:** Edumatrix, EMAS, app-store reviews, or press coverage of student complaints. The only criticism found is in accreditation reports.

### 2. State systems
- **"Tələbə-məzun":** Presidential Decree 225 of 23.02.2010. The State Examination Center administers it and connection is mandatory for every university. Universities enter changes within 10 days through operator workstations running the Center's software; the regulation mentions no API. [VERIFIED: https://frameworks.e-qanun.az/19/c_f_19269.html]
- **TMİS (ministry central system):** accreditation applications go only through it. [VERIFIED: https://tkta.edu.az/az/services/accreditation] Accreditation indicator 5.4.7 scores how well the university's system integrates with it. [VERIFIED: https://frameworks.e-qanun.az/52/f_52566.html]
- **digital.login:** single sign-on for state and private platforms, via SİMA İmza, ID number, ASAN İmza or mygov QR. [VERIFIED: https://idda.az/az/xeberler/vetendaslar-artiq-digitallogin-e-inteqrasiya-olunmus-butun-platformalara-mygov-ile-daxil-ola-bilecekler] Its renaming to "mygov ID", with 4.8 million users and 240+ systems, is [UNVERIFIED (snippet)].
- **SİMA and ASAN İmza:** SİMA is run by AzInTelecom and was added to etender.gov.az in October 2026. [UNVERIFIED (snippet)]
- **Not found:** public developer documentation or onboarding rules for mygov ID, SİMA, ASAN İmza or the e-government gateway. Integration appears to be by agreement with IDDA or AzInTelecom.

### 3. Law and regulation
- **Personal Data Law 998-IIIQ, consent (Art. 8):** written consent or an e-document with enhanced e-signature; the burden of proof is on the owner or operator. Lawful bases are in Art. 9.6. [VERIFIED: https://frameworks.e-qanun.az/19/f_19675.html]
- **Biometrics (Art. 9.5):** face image, voice, fingerprints and handwriting are fully covered. [VERIFIED: same]
- **Cross-border transfer (Art. 14):** banned if the destination lacks equivalent protection, unless the subject consents. [VERIFIED: same]
- **State registration (Art. 15):** a personal-data information system must be registered before processing; staff-only systems are exempt. [VERIFIED: same]
- **Data localisation:** none seen in the articles read (2, 5, 8–10, 13–17). The registration-threshold decisions were not read.
- **Government Cloud:** Decree 718 (03.06.2019) defines "state bodies" to include public legal entities and requires them to place state information systems in the G-Cloud. [VERIFIED: https://president.az/az/articles/view/33423] The transition plan (Cabinet Decision 428, 29.10.2020) names BDU, UNEC and the Languages University; AzTU is not on the list. [VERIFIED: https://frameworks.e-qanun.az/46/f_46243.html]
- **Security diagnostics:** Cabinet Decision 372 (05.11.2026) has the state security service (XRİTDX) assess public legal entities on four criteria, including suppliers and software/data security. [VERIFIED: https://operativmedia.az/post/147294/dovlet-qurumlarinin-informasiya-tehlukesizliyi-muhitinin-diaqnostikasinin-heyata-kecirilmesi-xri-tdx-e-hevale-edilib]
- **Credit rules (Cabinet Decision 348, 24.12.2013):** a student absent from more than 25% of a course's class hours is barred from the exam, and the university may lower that limit (3.2.23). Tutors and individual study plans are required. [VERIFIED: https://adpu.edu.az/images/adpu_files/universitet/normativ-senedler/ali-tehsilin-muessilelerinin-bakalavriat-ve-magistratura-seviyyelerinde-kredit-sistemi-ile-tedrisin-teskili-qaydalari.pdf]
- **AzTU grading:** seminar 30, attendance 10, independent work 10, exam 50; minimum 17 in the exam; A–F scale; exams are video-recorded and centrally monitored. [VERIFIED: https://www.aztu.edu.az/az/telebeler/tedris-teqvimi-ve-qaydalar/qiymetlendirme-ve-imtahan-teskili-qaydalari] The national source (ministry Order 1060, 11.09.2008) is [UNVERIFIED (snippet)].
- **Not found:** mandatory syllabus contents, or national rules on online exams and QR e-certificates.
- **Accreditation criteria (ministry decision KQ-05, 30.09.2022):** [VERIFIED: https://frameworks.e-qanun.az/52/f_52566.html]
  - 3.5.1: an e-learning management system with synchronous and asynchronous learning and assessment.
  - 3.5.3: a platform and journal logging student activity.
  - 4.4: anti-plagiarism tools.
  - 5.4.2–5.4.8: system coverage, role separation, student usage, TMİS integration, security and maintenance contracts.
- **Accreditation cycle:** every five years, with a 20,000 AZN fee. [VERIFIED: https://tkta.edu.az/az/services/accreditation]
- **AI Strategy 2025–2028 (approved 19.03.2025):** goals include ethics and regulatory rules, data privacy, bias prevention and new university curricula. [VERIFIED: https://idda.az/az/xeberler/suni-intellekt-strategiyasi-tesdiq-edildi-neler-gozlenilir ; https://banker.az/suni-intellekt-strategiyasinin-m%C9%99qs%C9%99dl%C9%99ri-aciqlanib/] No education-specific AI guidance was found.

### 4. Procurement and money
- **Public Procurement Law 988-VIQ (in force 01.01.2024):** [VERIFIED: https://frameworks.e-qanun.az/54/f_54966.html]
  - Public legal entities are procuring entities.
  - 100,000 AZN and above requires an open or two-stage tender.
  - Below 100,000 AZN a quotation request is allowed; up to 30,000 AZN it is limited to micro and small firms.
  - Single-source needs the control body's consent (for example exclusive rights, or continuation of an earlier purchase).
  - Unplanned purchases up to 10,000 AZN a year are exempt (20,000 for some entities).
  - Purchases funded by international organisations follow the donor's rules.
- **Practice at Baku Engineering University:** a tender commission is set up by rector's order, at least three price quotes are collected, and the tender is published on etender.gov.az. [VERIFIED: BMU report above]
- **Decision makers:** AzTU has a vice-rector for digitalisation and an IT Department under the rector. [VERIFIED: AzTU TKTA report; https://www.aztu.edu.az/az/haqqimizda/rehbetlik-ve-idareetme/rektor]
- **Sales cycle:** no source; unknown. [UNVERIFIED]
- **Erasmus+:** informally suspended in Azerbaijan in April 2025 (27 projects, about 20 million AZN, 32 universities). [VERIFIED: https://abzas.org/en/2025/4/erasmus-activities-have-bee50216bdf-1]
- **Not found:** published contract values for any LMS or e-university system (only the KOICA grant), and any IDDA or World Bank programme funding university portals.

### 5. AzTU facts
- **Size:** 6 faculties, 21 departments, 121+ specialities, 10,000+ students, 1,000+ academic staff. [VERIFIED: https://www.aztu.edu.az/az]
- **Faculties:** IT and Telecommunications; Industrial Economics and Management; Special Technique and Technology; Machine-building and Metallurgy; Transport and Logistics; Energetics. [VERIFIED: same]
- **Contact:** H. Cavid prospekti 25, Baku AZ1073; (+994 12) 539-13-05; aztu@aztu.edu.az; Mon–Fri 09:00–18:00. [VERIFIED: https://www.aztu.edu.az/az/elaqe]
- **Campus:** seven multi-storey buildings on one compact site; VI and VII are adjoined. [VERIFIED: AzTU TKTA report]
- **Rector:** Vilayət Vəliyev, appointed 31.07.2019 and reconfirmed in 2024. His message prioritises AI, IoT and cybersecurity. [VERIFIED: rector page above]
- **Strategy:** Vision 2030 has a "Digital Transformation / Digital University" pillar (IT modernisation, automated management, digital learning tools). [VERIFIED: https://www.aztu.edu.az/az/haqqimizda/vizyon-ve-missiya/strateji-plan]
- **Quality unit:** surveys run on Google Forms; general student satisfaction is 76.4%. [VERIFIED: https://www.aztu.edu.az/az/kts]

### 6. Competitors and substitutes
- **Local:** Unibook (broad modules, state-aligned), EduMan (UNEC ecosystem with QR certificates), Empro, Cybernet, Blackboard, and the free ministry Microsoft/Copilot bundle. Sources as in section 1.
- **Their visible weakness:** no AI tutor or assistant advertised. This is my inference. [UNVERIFIED]
- **Regional:** [UNVERIFIED (snippets)]
  - HEMIS (Uzbekistan): state-mandated, World Bank-funded, about 170 universities; slowdowns reported.
  - Platonus (Kazakhstan): strong registrar functions, weak distance learning.
  - Proliz OBS (Türkiye): 106+ universities; a 2025 national vulnerability advisory.

### Top 10 implications for the product
1. Position it as closing AzTU's documented gaps (timetables, e-journal, appeals, e-documents) and feeding the planned UMS, not as "another LMS".
2. Ship an accreditation evidence pack mapped to indicators 3.5.1, 3.5.3, 4.4 and 5.4.2–5.4.8: usage statistics, role matrix, security documents, integration list.
3. Build export and reconciliation for "Tələbə-məzun" (10-day rule) and an integration path to TMİS.
4. Capture consent as the law requires, keep proof, and prepare the university's state-registration dossier for the system.
5. Treat face or voice proctoring as biometric processing; offer a non-biometric exam mode (seating, video, lockdown).
6. Offer hosting in Azerbaijan or the G-Cloud; make foreign AI APIs opt-in with explicit cross-border consent, pseudonymisation and a local-model option.
7. Be ready for XRİTDX diagnostics: supplier security, audit logs, backups.
8. Hard-code the national rules but keep them configurable: 25% absence block, 30/10/10/50 split, exam minimum 17, A–F scale, 40-credit cap.
9. Support SSO with AzTU's own SSO and Microsoft 365, plus mygov ID; issue QR-verifiable, e-signed certificates.
10. Price for procurement: a pilot under the exemption or below 100,000 AZN for a quotation request, a single-source justification afterwards, and no reliance on Erasmus+ money.
