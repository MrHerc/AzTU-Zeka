-- Task 20, after the Checkpoint F language review: a database seeded before still holds texts that are no longer
-- translation keys, so en and ru readers saw them in Azerbaijani (M1). 0463 rewrote the e-service, academy, tool and news
-- texts and missed the seeded support desk; the review then renamed time clauses (-dıqda), the academy's levels and two
-- e-service outcomes. A column changes only while it still holds the old seeded text, so nothing a person wrote is touched.
UPDATE support_tickets SET subject = 'Profildə köhnə qrupum göstərilir' WHERE subject = 'Profildə qrupum köhnə göstərilir';
UPDATE support_tickets SET subject = 'Kampus köməkçisi təqaüd sualıma cavab vermədi' WHERE subject = 'Kampus köməkçisi təqaüd barədə';
UPDATE support_tickets SET body = 'Elektrik dövrələri fənnində tutorun cavabındakı [2] mənbəyinə klik etdikdə pəncərə açılmır.'
  WHERE body IN ('Elektrik dövrələri fənnində tutorun cavabındakı [2] mənbəsinə klik edəndə pəncərə açılmır.',
                 'Elektrik dövrələri fənnində tutorun cavabındakı [2] mənbəyinə klik edəndə pəncərə açılmır.');
UPDATE support_tickets SET body = '«Dəyişən cərəyan» mühazirəsini PPTX formatında yüklədim, amma bəzi slaydların mətni tutorda görünmür.'
  WHERE body = '“Dəyişən cərəyan” mühazirəsini PPTX formatında yüklədim, amma bəzi slaydların mətni tutorda görünmür.';
UPDATE support_messages SET text = 'Sorğunuz qəbul olundu, araşdırırıq.' WHERE text = 'Müraciətiniz qəbul olundu, araşdırırıq.';
UPDATE academy_tracks SET level = 'Başlanğıc səviyyə' WHERE level = 'Başlanğıc';
UPDATE academy_tracks SET level = 'Orta səviyyə' WHERE level = 'Orta';
UPDATE request_types SET outcome = 'Yeni bilet hazır olduqda bildiriş gələcək; bileti dekanlıqdan götürəcəksiniz.'
  WHERE code = 'student_card' AND outcome = 'Yeni bilet hazır olanda bildiriş gələcək; bileti dekanlıqdan götürəcəksiniz.';
UPDATE request_types SET outcome = 'İcazə təsdiqləndikdə seçilmiş fənlərin müəllimləri avtomatik məlumatlandırılır.'
  WHERE code = 'leave_permission' AND outcome = 'İcazə təsdiqlənəndə seçilmiş fənlərin müəllimləri avtomatik məlumatlandırılır.';
