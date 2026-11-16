# Təhlükəsiz imtahan brauzeri (SEB)

> Araşdırma agentinin yekun hesabatı, olduğu kimi. Tarix: 2026-11-16.
> `[VERIFIED: url]` = agent səhifəni açıb oxuyub. `[UNVERIFIED]` = yaddaşdan və ya zəif mənbədən.
> Agentin öz metod qeydlərinə baxın: bəzi rəsmi saytlar birbaşa açılmayıb.

SECURE EXAM MODE RESEARCH (as of 2026-11-16)

Access note: this sandbox could not fetch safeexambrowser.org, docs.moodle.org or readthedocs directly. [VERIFIED] means I read the primary source (SEB and Moodle source on GitHub). [EXCERPT] means a search-engine excerpt of the named page, not read in full. [UNVERIFIED] means general knowledge.

Source legend:
- WIN = github.com/SafeExamBrowser/seb-win-refactoring (master)
- MAC = github.com/SafeExamBrowser/seb-mac
- MDL = github.com/moodle/moodle/tree/main/public/mod/quiz/accessrule/seb
- SRV = github.com/SafeExamBrowser/seb-server
- DEV = safeexambrowser.org/developer/seb-config-key.html

1. SEB VERSIONS, PLATFORMS, LICENCE
- Windows: 3.10.3 (released 02 Nov; year not shown on the page). Needs Windows 10 1803+. The Browser Exam Key differs between x86 and x64 builds. [VERIFIED: WIN/releases]
- macOS: 3.7.2 (04 Nov); default minimum macOS 12 since 3.7.1. [VERIFIED: MAC/releases]
- iOS/iPadOS: 3.6.2 (3 Mar 2026) [EXCERPT: safeexambrowser.org/news_en.html]. A 3.7.1 iOS mention is [UNVERIFIED].
- Android, ChromeOS, Linux: no official build; the overview lists only Windows/macOS/iOS [EXCERPT: safeexambrowser.org/about_overview_en.html]. Community Linux ports are unofficial.
- Licence: MPL-2.0 [VERIFIED: WIN, SRV]. Commercial use and shipping your own .seb files are fine; modified SEB source files must stay MPL [UNVERIFIED legal reading]. The Windows build reportedly includes a closed-source integrity module, so self-builds get different keys [EXCERPT].
- SEB Alliance membership is optional, but integration support depends on contribution level; the company tier is listed at EUR 25,000 [EXCERPT: safeexambrowser.org/alliance/fees.html]. Do not imply endorsement.

2. SERVER-SIDE VERIFICATION
- Headers: `X-SafeExamBrowser-ConfigKeyHash` and `X-SafeExamBrowser-RequestHash`. Moodle reads them as `HTTP_X_SAFEEXAMBROWSER_CONFIGKEYHASH` / `..._REQUESTHASH` and checks `hash('sha256', $url.$key) === $received`. [VERIFIED: MDL/classes/seb_access_manager.php]
- Client computation: SHA-256 over UTF-8 of (absolute request URL with only the `#fragment` removed + key), lowercase hex. There is no other normalisation, so the query string and trailing slash count. [VERIFIED: WIN/SafeExamBrowser.Configuration/Cryptography/KeyGenerator.cs; MAC SEBBrowserController.m]
- Windows still sends headers, only when `sendBrowserExamKey` is true and only on main-frame or same-host requests. [VERIFIED: WIN/.../Handlers/ResourceHandler.cs]
- macOS/iOS with the modern WebView (WKWebView) cannot send headers; the JS API is the only path. [EXCERPT: safeexambrowser.org/download_en.html]
- JS API: `SafeExamBrowser.security.configKey`, `.browserExamKey`, `.updateKeys(callback)`, and `SafeExamBrowser.version`. There is no `appVersion` property. [VERIFIED: WIN/SafeExamBrowser.Browser/Content/Api.js]
- JS API availability: macOS/iOS 3.0+; Windows 3.4 per the news page, 3.3.2 per DEV (the sources conflict). macOS 3.6 fills the keys at page load without `updateKeys`. [EXCERPT]
- The JS values are already hashed with the frame URL. [VERIFIED: WIN/.../RenderProcessMessageHandler.cs]
- Config Key derivation [VERIFIED: MDL/classes/property_list.php, config_key.php]:
  1. Parse the plist and drop `originatorVersion`.
  2. Remove empty dicts; keep arrays in order.
  3. Convert data to a Base64 string and dates to ISO 8601.
  4. Sort dict keys recursively, case-insensitively (Moodle uses ICU root collation).
  5. Emit compact JSON with no whitespace and unescaped `/` and Unicode.
  6. SHA-256, lowercase hex.
- SEB hashes only the keys present in the opened file, so the server can compute the key from the file it generates. [EXCERPT: DEV]
- Practical key: the Config Key, which is independent of version and platform. The Browser Exam Key changes per SEB version, build and config, and must be copied by hand, so it suits only pinned lab installs.
- Pseudo-code:
```
def verify(exam, sess, url, ck, bek=None):      # url = header-request URL or JS location.href
    u = urlsplit(url)
    if (u.scheme, u.netloc) != PUBLIC_ORIGIN: return False
    if not u.path.startswith(f"/exam/{exam.id}/"): return False
    base = url.split('#')[0]
    h = lambda k: sha256((base + k).encode()).hexdigest()
    if not compare_digest(h(exam.config_key), ck.lower()): return False
    if exam.allowed_beks and not any(compare_digest(h(b), bek or "") for b in exam.allowed_beks): return False
    sess.seb_verified_exam = exam.id; return True
```
- Pitfalls:
  - Behind a reverse proxy, rebuild the public scheme, host and exact query string.
  - Each redirect target is hashed with its own URL.
  - In an SPA, capture `location.href` at load, before pushState routing changes it (my inference from the code).
  - Moodle treats a key value of `":"` as unset. [VERIFIED: MDL/amd/src/validate_quiz_access.js]
  - A User-Agent containing "SEB" proves nothing.
  - Put a per-session nonce in the verified URL to stop replay of a captured hash.

3. .seb FILES
- Format: Apple plist XML. It can be wrapped as gzip → 4-char prefix (`pswd`, `pwcc`, `plnd`, `pkhs`) → RNCryptor/AES-256 → gzip. [EXCERPT: safeexambrowser.org/developer/seb-file-format.html]
- Moodle serves the config as `Content-Type: application/seb`, `attachment; filename=config.seb`, no-cache. [VERIFIED: MDL/classes/helper.php]
- Whether a plain XML file is accepted without the wrapper was not confirmed; test it.
- Key names [VERIFIED: WIN/SafeExamBrowser.Configuration/ConfigurationData/Keys.cs]:
  - Navigation: `startURL`, `startURLAppendQueryParameter`, `quitURL`, `quitURLConfirm`, `allowQuit`.
  - Quit password: `hashedQuitPassword`, SHA-256 hex of the password (per Moodle).
  - URL filter: `URLFilterEnable`, `URLFilterEnableContentFilter`, `URLFilterRules[{action 1=allow/0=block, active, expression, regex}]`.
  - Keys: `sendBrowserExamKey`, `examKeySalt`.
  - Kiosk: `createNewDesktop`, `killExplorerShell`.
  - Lockdown: `allowVirtualMachine`, `clipboardPolicy`, `enablePrintScreen`, `allowScreenSharing`, `permittedProcesses`, `prohibitedProcesses`, `allowedDisplaysMaxNumber`, `allowDeveloperConsole`, `allowDownloads`.
  - Other: `sebConfigPurpose`, `sebAllowedVersions`.
- Moodle forces `startURL`, `sendBrowserExamKey=true`, `browserWindowWebView=3`. [VERIFIED: MDL/classes/seb_quiz_settings.php]
- Launch: a `seb://` (http) or `sebs://` (https) link to the config URL. [VERIFIED: MDL/classes/link_generator.php]
- A config behind login loads only when the link is opened inside SEB. A query string on the link is appended to the start URL if the option is enabled. [EXCERPT: SEB manuals]
- Libraries: no maintained PyPI/npm package found. Generate with Python `plistlib` and write about 40 lines for the Config Key. Moodle's PHP is GPL, so re-implement it. Check the result against the key the SEB Config Tool shows.

4. SEB SERVER (v3.0.x; Java/Docker)
- Adds central configs, LMS connectors (Moodle, Open edX, OLAT, Ans), live client monitoring, "Quit SEB" instructions, App-Signature-Key integrity grants and screen proctoring.
- Zoom/Jitsi live proctoring was removed in 2.0.
- Not needed for v1.
[VERIFIED: SRV README, docs/monitoring.rst, docs/exam_ask.rst]

5. MOODLE quizaccess_seb (reference flow)
- Teacher picks one of: No / Configure manually / Use template / Upload config / Use SEB client config.
- Teacher options include download button, quit link and password, reload, taskbar, URL filter expressions and allowed Browser Exam Keys. [VERIFIED: MDL/lang/en/quizaccess_seb.php]
- The server builds the plist and stores its Config Key.
- The student sees "Launch SEB" (sebs:// to `config.php?cmid=`), "Download SEB" and "Download config".
- Inside SEB, the JS posts `{cmid, url, configkey, browserexamkey}` to a web service.
- Check order: basic header (client-config mode only) → Config Key → Browser Exam Keys.
- Success sets a session flag, which is cleared when the attempt finishes.
[VERIFIED: MDL/rule.php, classes/external/validate_quiz_keys.php]

6. WEAKNESSES
- Anyone holding the .seb can compute the Config Key hash and present it from an ordinary browser. [VERIFIED: github.com/Chiogros/nSEA]
- VM and remote-tool detection is an arms race: 3.10.2 added remote-tool blocks, 3.10.3 fixed VM false positives. [VERIFIED: WIN/releases]
- SEB Server's own docs anticipate modified clients. [VERIFIED: SRV docs/exam_ask.rst]
- A second device, a phone camera or an HDMI capture/KVM is invisible to any lockdown browser. [UNVERIFIED]
- What matters more: invigilated rooms, IP allow-listing, per-student randomisation from pools, one active session, server-authoritative timer, autosave/resume, hash-chained audit log, focus events as signals only, and post-exam similarity analysis. [UNVERIFIED: professional judgment]

7. ALTERNATIVES (all quote-based pricing)
- Respondus: annual campus licence with unlimited use; Monitor is a per-seat add-on with 200 seats free. [EXCERPT: web.respondus.com]
- Proctorio and Honorlock: browser extension plus LTI; institutional or per-student/exam contracts. [EXCERPT, third-party]
- Examplify and TestWe: proprietary offline apps tied to their own platforms. [EXCERPT]
- Inspera: a full platform with its own lockdown browser. [EXCERPT]
- None offers an open protocol for a custom portal. [UNVERIFIED]
- Legal cases:
  - Ogletree v. Cleveland State (N.D. Ohio, 22 Aug 2022): a room scan was an unreasonable search. [EXCERPT: law.justia.com]
  - Italian Garante fined Bocconi €200,000 (2021) for biometric processing without a lawful basis; consent was rejected. [EXCERPT: edpb.europa.eu]
  - Amsterdam court (June 2020) allowed Proctorio, noting no biometric processing. [EXCERPT]
  - A French court suspended TestWe. [EXCERPT: techdirt.com]
- Avoid by default: webcam, audio or screen recording, face or ID matching, room scans, and automated penalties. Keep `enableScreenProctoring` off. Log only IP, user agent and timestamps, with a retention limit.

8. STANDARDS
- ISO/IEC 23988:2007 is current; a second edition is in draft. [EXCERPT: iso.org/standard/87987.html]
- QTI 3.0 final was released May 2022. [EXCERPT: 1edtech.org]
- Accessibility: NVDA and JAWS do not work with the "Create New Desktop" kiosk mode. [VERIFIED: WIN/releases 3.10.3]
- Per-student extra time, a mock exam with the real config, load testing, a deploy freeze, a pinned SEB version, a paper fallback and an incident log. [UNVERIFIED]

9. BROWSER-ONLY FALLBACK
- Fullscreen needs a user gesture and the user can always leave it. [EXCERPT: developer.chrome.com keyboard-lock]
- It can log visibilitychange/blur/fullscreen-exit and deter copy/paste. [UNVERIFIED]
- It cannot block other apps, extensions, screenshots, VMs or second devices. [UNVERIFIED]
- The real guarantees are server-side: single session, timer and audit.

RECOMMENDED DESIGN FOR A 3-DAY V1
1. Data model.
   - Exam: `secure_mode` (off / browser_only / seb_required), `seb_config_xml`, `seb_config_key`, `seb_allowed_beks[]`, `quit_password_hash`, `config_token`, `allowed_cidrs[]`.
   - Attempt: `seb_verified_at`, `seb_version`, `active_session_id`, `deadline_at`, `extra_minutes`, `order_seed`.
   - AuditEvent: `prev_hash`, `hash`, `ts`, `type`, `payload`.
2. Config generation. Build one static plist per exam on save:
   - `startURL=https://host/exam/{id}/start` (a real page load);
   - URL filter allowing only exam, API and static paths;
   - `quitURL`, `hashedQuitPassword`, `sendBrowserExamKey=true`, `browserWindowWebView=3`, `allowVirtualMachine=false`.
   Then compute and store the Config Key.
3. `GET /exams/{id}/config.seb?k={config_token}`. It needs no cookie (SEB fetches it itself) and returns `application/seb`. The UI shows a `sebs://` launch link, an SEB download link and a config download.
4. The student logs in inside SEB. A one-time token via `startURLAppendQueryParameter` can come later.
5. `POST /api/exams/{id}/seb-verify {url, configKey, browserExamKey, version}` runs the pseudo-code above. Also validate the headers on the start page when present.
6. Middleware. This is the actual "only the exam" guarantee:
   - a `seb_required` exam rejects sessions without `seb_verified_exam == id`;
   - a verified session gets 403 on every non-exam route.
7. One active session per attempt, server-side deadline, autosave every N seconds with resume, IP allow-list, audit log.
8. UI states: SEB required → verifying → verified/start → failed (with reason) → in exam (server timer, save status, offline banner) → submitted with "Quit SEB" → blocked (other session / IP).
9. Day 3: test on Windows x64, macOS and iPad with the current SEB, and run a mock exam.

WHAT MUST NOT BE CLAIMED TO CUSTOMERS
- "Cheat-proof" or "impossible to bypass".
- That the server can prove a genuine, unmodified SEB. The Config Key proves knowledge of the config only.
- Any protection against phones, second devices, cameras or hardware capture, or guaranteed VM detection.
- Support for Android, Chromebook or Linux.
- That the browser-only fallback is a lockdown.
- That focus-loss logs prove misconduct.
- "Proctoring" or identity verification.
- ETH/SEB endorsement.
