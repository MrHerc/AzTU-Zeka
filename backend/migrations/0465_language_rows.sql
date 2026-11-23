-- Task 20, Checkpoint F's M1 leftovers: rows a database seeded before the language change still holds in the old wording.
-- 0463 and 0464 brought the catalogue's seeded texts; this brings the rows that carry their own texts: notifications,
-- Radar support plans and the e-service answers (their en and ru are set together with the az), the demo's synthetic tutor
-- messages and course suggestions, and the question bank's quotes («», i18n/STYLE.md). A value changes only while it still
-- holds the old seeded text: a row someone wrote or edited is left alone. 0463 and 0464 are not edited.
UPDATE notifications SET title = replace(title, '"az": "Hakaton: “AzTU AI Challenge 2026” — qeydiyyat açıqdır"', '"az": "Hakaton: «AzTU AI Challenge 2026» — qeydiyyat açıqdır"')
  WHERE instr(title, '"az": "Hakaton: “AzTU AI Challenge 2026” — qeydiyyat açıqdır"') > 0;
UPDATE notifications SET body = replace(body, '"az": "“Təhsildə süni intellekt” istiqaməti"', '"az": "«Təhsildə süni intellekt» istiqaməti"')
  WHERE instr(body, '"az": "“Təhsildə süni intellekt” istiqaməti"') > 0;
UPDATE notifications SET body = '{"az": "7 göstərici hədəfə çatıb", "en": "7 indicators are on target", "ru": "7 показателей достигли целевого значения"}'
  WHERE body = '{"az": "Göstəricilərin 7-si hədəfdədir", "en": "7 of the indicators are on target", "ru": "7 из показателей достигли цели"}';
UPDATE interventions SET plan = replace(plan, '"az": "Növbəti 2 dərsdə iştirak edin. Üzrlü səbəbiniz olubsa, təsdiqedici sənədi E-xidmətlərdən yükləyin — qayıb üzrlü sayılacaq."', '"az": "Növbəti 2 dərsdə iştirak edin. Üzrlü səbəbiniz olubsa, təsdiqedici sənədi E-xidmətlər bölməsində yükləyin — qayıb üzrlü hesab ediləcək."')
  WHERE instr(plan, '"az": "Növbəti 2 dərsdə iştirak edin. Üzrlü səbəbiniz olubsa, təsdiqedici sənədi E-xidmətlərdən yükləyin — qayıb üzrlü sayılacaq."') > 0;
UPDATE interventions SET plan = replace(plan, '"ru": "Посетите следующие 2 занятия. Если причина была уважительной, загрузите подтверждающий документ в электронных услугах — пропуск будет засчитан как уважительный."', '"ru": "Посетите следующие 2 занятия. Если у вас была уважительная причина, загрузите подтверждающий документ в разделе «Электронные услуги» — пропуск будет признан уважительным."')
  WHERE instr(plan, '"ru": "Посетите следующие 2 занятия. Если причина была уважительной, загрузите подтверждающий документ в электронных услугах — пропуск будет засчитан как уважительный."') > 0;
UPDATE requests SET answer = replace(answer, 'Zəka-da başqa heç bir qeyd dəyişməyib.", "en": "', 'Zəka platformasında başqa heç bir qeyd dəyişdirilməyib.", "en": "')
  WHERE instr(answer, 'Zəka-da başqa heç bir qeyd dəyişməyib.", "en": "') > 0 AND instr(answer, '{"az": "Müraciətiniz qeydə alınıb. Baxan bölmə: ') = 1;
UPDATE courses SET suggestions = replace(suggestions, '"“used to” və “used for” fərqi nədir?"', '"«used to» və «used for» fərqi nədir?"')
  WHERE instr(suggestions, '"“used to” və “used for” fərqi nədir?"') > 0;
UPDATE messages SET content = '«used to» və «used for» fərqi nədir?'
  WHERE synthetic = 1 AND content = '“used to” və “used for” fərqi nədir?';
UPDATE courses SET suggestions = replace(suggestions, '"“consists of” necə işlədilir?"', '"«consists of» necə işlədilir?"')
  WHERE instr(suggestions, '"“consists of” necə işlədilir?"') > 0;
UPDATE messages SET content = '«consists of» necə işlədilir?'
  WHERE synthetic = 1 AND content = '“consists of” necə işlədilir?';
UPDATE messages SET content = replace(replace(content, '“', '«'), '”', '»')
  WHERE synthetic = 1 AND role = 'assistant' AND instr(content, 'Materialda deyilir: “') > 0;
UPDATE questions SET text = 'Doğrudurmu: «Paralel birləşmədə ekvivalent müqavimət ən kiçik müqavimətdən də kiçik olur».'
  WHERE text = 'Doğrudurmu: “Paralel birləşmədə ekvivalent müqavimət ən kiçik müqavimətdən də kiçik olur.”';
UPDATE questions SET text = 'Doğrudurmu: «a[-1] ifadəsi siyahının ilk elementini qaytarır».'
  WHERE text = 'Doğrudurmu: “a[-1] ifadəsi siyahının ilk elementini qaytarır.”';
UPDATE questions SET text = 'Doğrudurmu: «Funksiyanın nöqtədəki törəməsi həmin nöqtədə qrafikə çəkilmiş toxunanın bucaq əmsalına bərabərdir».'
  WHERE text = 'Doğrudurmu: “Funksiyanın nöqtədəki törəməsi həmin nöqtədə qrafikə çəkilmiş toxunanın bucaq əmsalına bərabərdir.”';
UPDATE questions SET text = 'Doğrudurmu: «Tezlik artdıqca induktiv müqavimət azalır».'
  WHERE text = 'Doğrudurmu: “Tezlik artdıqca induktiv müqavimət azalır.”';
UPDATE questions SET text = 'Doğrudurmu: «open() funksiyasının "w" rejimi faylın sonuna yeni məlumat əlavə edir».'
  WHERE text = 'Doğrudurmu: “open() funksiyasının "w" rejimi faylın sonuna yeni məlumat əlavə edir.”';
UPDATE questions SET text = 'Doğrudurmu: «∫ xⁿ dx = xⁿ⁺¹ / (n + 1) + C düsturu n = −1 halında da tətbiq olunur».'
  WHERE text = 'Doğrudurmu: “∫ xⁿ dx = xⁿ⁺¹ / (n + 1) + C düsturu n = −1 halında da tətbiq olunur.”';
UPDATE questions SET text = 'Doğrudurmu: «Nyutonun üçüncü qanunundakı təsir və əks-təsir qüvvələri eyni cismə tətbiq olunduğu üçün bir-birini tarazlaşdırır».'
  WHERE text = 'Doğrudurmu: “Nyutonun üçüncü qanunundakı təsir və əks-təsir qüvvələri eyni cismə tətbiq olunduğu üçün bir-birini tarazlaşdırır.”';
UPDATE questions SET text = 'Doğrudurmu: «1:2 miqyasında çəkilmiş çertyojda ölçü rəqəmi kimi kiçildilmiş ölçü yazılır».'
  WHERE text = 'Doğrudurmu: “1:2 miqyasında çəkilmiş çertyojda ölçü rəqəmi kimi kiçildilmiş ölçü yazılır.”';
UPDATE questions SET explanation = '«is used to» quruluşundan sonra felin əsas forması gəlir: is used to limit.'
  WHERE explanation = '“is used to” quruluşundan sonra felin əsas forması gəlir: is used to limit.';
UPDATE questions SET text = '«The circuit ___ a battery, a switch and two resistors.»'
  WHERE text = '“The circuit ___ a battery, a switch and two resistors.”';
UPDATE questions SET explanation = '«consists of» quruluşu düzgündür: The circuit consists of …'
  WHERE explanation = 'Düzgün quruluş “consists of”-dur: The circuit consists of …';
UPDATE questions SET text = 'Doğrudurmu: «İngilis dilində 3,5 kΩ yazılışı düzgündür».'
  WHERE text = 'Doğrudurmu: “İngilis dilində 3,5 kΩ yazılışı düzgündür.”';
UPDATE questions SET text = '«25 ± 0.05 mm» necə oxunur?'
  WHERE text = '“25 ± 0.05 mm” necə oxunur?';
UPDATE questions SET explanation = '± işarəsi «plus or minus», 0.05 isə «zero point zero five» kimi oxunur.'
  WHERE explanation = '± işarəsi “plus or minus”, 0.05 isə “zero point zero five” oxunur.';
UPDATE questions SET explanation = 'Düzgün variantlar: «The shaft is 40 mm long» və ya «The shaft has a length of 40 mm».'
  WHERE explanation = 'Düzgün variantlar: “The shaft is 40 mm long” və ya “The shaft has a length of 40 mm”.';
