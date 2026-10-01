"""Arayüz metinleri. Yeni dil eklemek için STRINGS'e aynı anahtarlarla yeni bir blok ekleyin
ve UI_LANGUAGES listesine adını yazın; eksik anahtarlar Türkçeye düşer."""

UI_LANGUAGES = [("tr", "Türkçe"), ("en", "English"), ("de", "Deutsch")]

STRINGS = {
    "tr": {
        "app_title": "Ders Transkript",
        "app_subtitle": "Ders kayıtlarını ve canlı konuşmayı metne çevirir.",
        "badge_offline": "●  İnternetsiz çalışır",
        "theme_system": "Sistem", "theme_light": "Açık", "theme_dark": "Koyu",
        "tab_file": "Ses dosyası", "tab_live": "Canlı dinleme",
        "side_by_side": "Yan yana", "side_by_side_tip": "İki paneli aynı anda göster",

        "drop_title": "Ses kaydını buraya sürükleyin",
        "drop_info": "veya dosya seçin  ·  MP3, M4A, WAV, OGG, OPUS ve video dosyaları",
        "choose_file": "Dosya seç", "change": "Değiştir",
        "file_dialog": "Ses dosyası seç", "filter_audio": "Ses/Video", "filter_all": "Tüm dosyalar",
        "unsupported_title": "Desteklenmeyen dosya",
        "unsupported_body": "Bu bir ses dosyası gibi görünmüyor. Yine de denenecek.",
        "dur_min_sec": "{m} dk {s} sn", "dur_sec": "{s} sn",

        "sec_language": "SES DİLİ", "sec_quality": "DOĞRULUK", "sec_mode": "ÇALIŞMA MODU",
        "lang_auto": "Otomatik algıla",
        "q_standard": "Standart", "q_high": "Yüksek",
        "q_standard_desc": "Daha hızlı ve hafif; net, gürültüsüz kayıtlar için yeterli.",
        "q_high_desc": "Önerilen. Ders kayıtlarında belirgin şekilde daha az hata yapar.",
        "mode_quiet": "Sessiz", "mode_balanced": "Dengeli", "mode_fast": "Hızlı",
        "mode_quiet_desc": "İşlemcinin yaklaşık dörtte birini kullanır; bu sırada bilgisayarda rahatça başka iş yapılabilir.",
        "mode_balanced_desc": "İşlemcinin yaklaşık yarısını kullanır; hız ile rahatlık arasında orta yol.",
        "mode_fast_desc": "İşlemcinin büyük kısmını kullanır; bu sürede bilgisayar yavaşlayabilir.",
        "timestamps": "Zaman damgaları ekle  [12:34]",

        "start_file": "Transkripte çevir", "cancel": "İptal et",
        "cancelling": "İptal ediliyor… (o anki parça bitince durur)",
        "step_model": "Model yükleniyor", "step_read": "Ses dosyası okunuyor",
        "step_transcribe": "Metne çevriliyor", "step_fmt": "Adım {i}/{n}  ·  {name}…",
        "k_audio": "İŞLENEN SES", "k_chunks": "PARÇA", "k_elapsed": "GEÇEN SÜRE", "k_eta": "KALAN SÜRE",
        "chunks_fmt": "{done} / {total}  ({left} kaldı)", "eta_calc": "hesaplanıyor…",
        "done_fmt": "✓  Tamamlandı  ·  {t} sürdü", "cancelled": "İptal edildi.",
        "error": "Hata oluştu.", "error_title": "Hata",
        "detected_lang": "Algılanan dil: {v}",
        "downloading_model": "Model ilk kez indiriliyor (bir kerelik, internet gerekir)…",
        "autosaved": "Otomatik kaydedildi: {path}", "saved": "Kaydedildi: {path}",

        "transcript": "TRANSKRİPT", "words_fmt": "·  {n} kelime",
        "save_txt": "Kaydet (.txt)", "copy_all": "Tümünü kopyala", "copied": "✓  Kopyalandı",
        "clear": "Temizle",
        "placeholder_file": "Transkript burada görünecek. Çevrildikçe metin akarak eklenir.",
        "placeholder_live": "Dinlemeyi başlatınca konuşulanlar birkaç saniye gecikmeyle burada belirir.",
        "save_dialog": "Kaydet", "filter_text": "Metin",
        "quit_title": "Çıkış", "quit_body": "Devam eden bir işlem var. Çıkılsın mı?",

        "sec_mic": "MİKROFON", "refresh_tip": "Mikrofon listesini yenile",
        "no_mic": "Mikrofon bulunamadı",
        "start_live": "Dinlemeyi başlat", "stop_live": "Durdur",
        "live_ready": "Hazır. Başlatınca mikrofon dinlenir ve metin canlı olarak yazılır.",
        "live_loading": "Model yükleniyor…", "live_listening": "Dinleniyor",
        "live_finishing": "Son parça metne çevriliyor…",
        "live_stopped": "Durduruldu  ·  {t} dinlendi",
        "save_recording": "Ses kaydını da sakla (Belgeler › Ders Transkript)",
        "recording_saved": "Ses kaydı: {path}",
        "k_listen": "DİNLEME SÜRESİ", "k_lag": "GECİKME", "k_level": "SES SEVİYESİ", "lag_fmt": "~{s} sn",
        "ui_lang_tip": "Arayüz dili",
        "lag_warn": "İşlemci yetişemiyor: 'Standart' doğruluk veya daha hızlı bir mod seçin.",
        "mic_denied": "Mikrofon izni verilmedi. Sistem Ayarları › Gizlilik ve Güvenlik › Mikrofon bölümünden izin verin.",
        "mic_error": "Mikrofon açılamadı.",
    },
    "en": {
        "app_title": "Lecture Transcriber",
        "app_subtitle": "Turns lecture recordings and live speech into text.",
        "badge_offline": "●  Works offline",
        "theme_system": "System", "theme_light": "Light", "theme_dark": "Dark",
        "tab_file": "Audio file", "tab_live": "Live listening",
        "side_by_side": "Side by side", "side_by_side_tip": "Show both panels at once",

        "drop_title": "Drop a recording here",
        "drop_info": "or choose a file  ·  MP3, M4A, WAV, OGG, OPUS and video files",
        "choose_file": "Choose file", "change": "Change",
        "file_dialog": "Choose an audio file", "filter_audio": "Audio/Video", "filter_all": "All files",
        "unsupported_title": "Unsupported file",
        "unsupported_body": "This does not look like an audio file. It will be tried anyway.",
        "dur_min_sec": "{m} min {s} s", "dur_sec": "{s} s",

        "sec_language": "SPOKEN LANGUAGE", "sec_quality": "ACCURACY", "sec_mode": "PERFORMANCE",
        "lang_auto": "Detect automatically",
        "q_standard": "Standard", "q_high": "High",
        "q_standard_desc": "Faster and lighter; good enough for clear, quiet recordings.",
        "q_high_desc": "Recommended. Makes noticeably fewer mistakes on lecture recordings.",
        "mode_quiet": "Quiet", "mode_balanced": "Balanced", "mode_fast": "Fast",
        "mode_quiet_desc": "Uses about a quarter of the CPU; the computer stays fully usable meanwhile.",
        "mode_balanced_desc": "Uses about half of the CPU; a middle ground between speed and comfort.",
        "mode_fast_desc": "Uses most of the CPU; the computer may feel slow meanwhile.",
        "timestamps": "Add timestamps  [12:34]",

        "start_file": "Transcribe", "cancel": "Cancel",
        "cancelling": "Cancelling… (stops after the current part)",
        "step_model": "Loading model", "step_read": "Reading audio file",
        "step_transcribe": "Transcribing", "step_fmt": "Step {i}/{n}  ·  {name}…",
        "k_audio": "AUDIO DONE", "k_chunks": "PARTS", "k_elapsed": "ELAPSED", "k_eta": "REMAINING",
        "chunks_fmt": "{done} / {total}  ({left} left)", "eta_calc": "estimating…",
        "done_fmt": "✓  Done  ·  took {t}", "cancelled": "Cancelled.",
        "error": "An error occurred.", "error_title": "Error",
        "detected_lang": "Detected language: {v}",
        "downloading_model": "Downloading the model for the first time (one-off, needs internet)…",
        "autosaved": "Saved automatically: {path}", "saved": "Saved: {path}",

        "transcript": "TRANSCRIPT", "words_fmt": "·  {n} words",
        "save_txt": "Save (.txt)", "copy_all": "Copy all", "copied": "✓  Copied",
        "clear": "Clear",
        "placeholder_file": "The transcript appears here, growing as it is transcribed.",
        "placeholder_live": "Once listening starts, speech appears here with a delay of a few seconds.",
        "save_dialog": "Save", "filter_text": "Text",
        "quit_title": "Quit", "quit_body": "A task is still running. Quit anyway?",

        "sec_mic": "MICROPHONE", "refresh_tip": "Refresh microphone list",
        "no_mic": "No microphone found",
        "start_live": "Start listening", "stop_live": "Stop",
        "live_ready": "Ready. Once started, the microphone is transcribed live.",
        "live_loading": "Loading model…", "live_listening": "Listening",
        "live_finishing": "Transcribing the last part…",
        "live_stopped": "Stopped  ·  listened for {t}",
        "save_recording": "Also keep the audio (Documents › Ders Transkript)",
        "recording_saved": "Recording: {path}",
        "k_listen": "LISTENING", "k_lag": "DELAY", "k_level": "INPUT LEVEL", "lag_fmt": "~{s} s",
        "ui_lang_tip": "Interface language",
        "lag_warn": "The CPU can't keep up: choose 'Standard' accuracy or a faster mode.",
        "mic_denied": "Microphone access was denied. Allow it in System Settings › Privacy & Security › Microphone.",
        "mic_error": "Could not open the microphone.",
    },
    "de": {
        "app_title": "Vorlesungs-Transkript",
        "app_subtitle": "Wandelt Vorlesungsaufnahmen und Live-Sprache in Text um.",
        "badge_offline": "●  Funktioniert offline",
        "theme_system": "System", "theme_light": "Hell", "theme_dark": "Dunkel",
        "tab_file": "Audiodatei", "tab_live": "Live-Mitschrift",
        "side_by_side": "Nebeneinander", "side_by_side_tip": "Beide Bereiche gleichzeitig anzeigen",

        "drop_title": "Aufnahme hierher ziehen",
        "drop_info": "oder Datei auswählen  ·  MP3, M4A, WAV, OGG, OPUS und Videodateien",
        "choose_file": "Datei wählen", "change": "Ändern",
        "file_dialog": "Audiodatei wählen", "filter_audio": "Audio/Video", "filter_all": "Alle Dateien",
        "unsupported_title": "Nicht unterstützte Datei",
        "unsupported_body": "Das sieht nicht nach einer Audiodatei aus. Es wird trotzdem versucht.",
        "dur_min_sec": "{m} Min. {s} Sek.", "dur_sec": "{s} Sek.",

        "sec_language": "GESPROCHENE SPRACHE", "sec_quality": "GENAUIGKEIT", "sec_mode": "LEISTUNG",
        "lang_auto": "Automatisch erkennen",
        "q_standard": "Standard", "q_high": "Hoch",
        "q_standard_desc": "Schneller und leichter; reicht für klare, ruhige Aufnahmen.",
        "q_high_desc": "Empfohlen. Macht bei Vorlesungsaufnahmen deutlich weniger Fehler.",
        "mode_quiet": "Leise", "mode_balanced": "Ausgewogen", "mode_fast": "Schnell",
        "mode_quiet_desc": "Nutzt etwa ein Viertel der CPU; der Rechner bleibt währenddessen voll nutzbar.",
        "mode_balanced_desc": "Nutzt etwa die Hälfte der CPU; ein Mittelweg zwischen Tempo und Komfort.",
        "mode_fast_desc": "Nutzt den Großteil der CPU; der Rechner kann währenddessen langsamer werden.",
        "timestamps": "Zeitstempel einfügen  [12:34]",

        "start_file": "Transkribieren", "cancel": "Abbrechen",
        "cancelling": "Wird abgebrochen… (nach dem aktuellen Teil)",
        "step_model": "Modell wird geladen", "step_read": "Audiodatei wird gelesen",
        "step_transcribe": "Wird transkribiert", "step_fmt": "Schritt {i}/{n}  ·  {name}…",
        "k_audio": "VERARBEITET", "k_chunks": "TEILE", "k_elapsed": "VERGANGEN", "k_eta": "VERBLEIBEND",
        "chunks_fmt": "{done} / {total}  (noch {left})", "eta_calc": "wird berechnet…",
        "done_fmt": "✓  Fertig  ·  Dauer {t}", "cancelled": "Abgebrochen.",
        "error": "Ein Fehler ist aufgetreten.", "error_title": "Fehler",
        "detected_lang": "Erkannte Sprache: {v}",
        "downloading_model": "Modell wird erstmalig heruntergeladen (einmalig, Internet nötig)…",
        "autosaved": "Automatisch gespeichert: {path}", "saved": "Gespeichert: {path}",

        "transcript": "TRANSKRIPT", "words_fmt": "·  {n} Wörter",
        "save_txt": "Speichern (.txt)", "copy_all": "Alles kopieren", "copied": "✓  Kopiert",
        "clear": "Leeren",
        "placeholder_file": "Das Transkript erscheint hier und wächst während der Verarbeitung.",
        "placeholder_live": "Nach dem Start erscheint das Gesprochene hier mit wenigen Sekunden Verzögerung.",
        "save_dialog": "Speichern", "filter_text": "Text",
        "quit_title": "Beenden", "quit_body": "Es läuft noch ein Vorgang. Trotzdem beenden?",

        "sec_mic": "MIKROFON", "refresh_tip": "Mikrofonliste aktualisieren",
        "no_mic": "Kein Mikrofon gefunden",
        "start_live": "Mitschrift starten", "stop_live": "Stopp",
        "live_ready": "Bereit. Nach dem Start wird das Mikrofon live transkribiert.",
        "live_loading": "Modell wird geladen…", "live_listening": "Hört zu",
        "live_finishing": "Letzter Teil wird transkribiert…",
        "live_stopped": "Gestoppt  ·  {t} aufgenommen",
        "save_recording": "Audio ebenfalls speichern (Dokumente › Ders Transkript)",
        "recording_saved": "Aufnahme: {path}",
        "k_listen": "AUFNAHMEDAUER", "k_lag": "VERZÖGERUNG", "k_level": "PEGEL", "lag_fmt": "~{s} s",
        "ui_lang_tip": "Sprache der Oberfläche",
        "lag_warn": "Die CPU kommt nicht hinterher: 'Standard'-Genauigkeit oder schnelleren Modus wählen.",
        "mic_denied": "Mikrofonzugriff verweigert. In Systemeinstellungen › Datenschutz & Sicherheit › Mikrofon erlauben.",
        "mic_error": "Mikrofon konnte nicht geöffnet werden.",
    },
}

_lang = "tr"


def set_lang(code):
    global _lang
    _lang = code if code in STRINGS else "tr"


def get_lang():
    return _lang


def tr(key, **kw):
    s = STRINGS[_lang].get(key) or STRINGS["tr"].get(key, key)
    return s.format(**kw) if kw else s
