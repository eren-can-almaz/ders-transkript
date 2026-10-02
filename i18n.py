"""Arayüz metinleri. Yeni dil eklemek için STRINGS'e aynı anahtarlarla yeni bir blok ekleyin
ve UI_LANGUAGES listesine adını yazın; eksik anahtarlar Türkçeye düşer."""

UI_LANGUAGES = [("tr", "Türkçe"), ("en", "English"), ("de", "Deutsch")]

STRINGS = {
    "tr": {
        "app_title": "Ders Transkript",
        "offline": "İnternetsiz çalışır",
        "months": "Ocak,Şubat,Mart,Nisan,Mayıs,Haziran,Temmuz,Ağustos,Eylül,Ekim,Kasım,Aralık",
        "theme_system": "Sistem", "theme_light": "Açık", "theme_dark": "Koyu",

        # kenar çubuğu
        "add_tip": "Yeni kayıt veya ses dosyası",
        "new_recording": "Yeni kayıt", "add_file": "Ses dosyası ekle…",
        "settings": "Ayarlar",
        "rec_title": "Kayıt {n}",
        "rec_busy": "Başka bir kayıt sürüyor. Mikrofon aynı anda tek kayıtta kullanılabilir; önce onu bitirin.",
        "badge_unsaved": "Kaydedilmedi", "badge_new": "Yeni",
        "empty_title": "Henüz kayıt yok",
        "empty_hint": "Yeni bir kayıt başlatın ya da bir ses dosyası ekleyin.\nDosyaları pencereye sürükleyip bırakabilirsiniz.",

        # kaydedici
        "rec_ready": "Başlatmak için kırmızı düğmeye basın",
        "st_recording": "Kaydediliyor", "st_paused": "Duraklatıldı",
        "st_loading": "Hazırlanıyor…  ses şimdiden kaydediliyor",
        "st_finishing": "Son parça işleniyor…",
        "rec_start_tip": "Kaydı başlat  (Ctrl+R)", "rec_stop_tip": "Kaydı bitir  (Ctrl+R)",
        "pause_tip": "Duraklat", "resume_tip": "Devam et", "play_tip": "Oynat",
        "live_text": "Canlı yazıya dök",
        "live_text_on": "Konuşulanlar ~2 sn içinde ekrana yazılır.",
        "live_text_off": "Yalnızca ses kaydedilir; işlemci neredeyse hiç kullanılmaz. Sonra 'Yazıya dök' ile çevirebilirsiniz.",
        "options": "Seçenekler", "mic": "Mikrofon", "no_mic": "Mikrofon bulunamadı",
        "mic_denied": "Mikrofon izni verilmedi. Sistem Ayarları › Gizlilik ve Güvenlik › Mikrofon bölümünden izin verin.",
        "mic_error": "Mikrofon açılamadı.",
        "lag_fmt": "Gecikme ~{s} sn",
        "lag_warn": "İşlemci yetişemiyor: 'Standart' doğruluk veya daha hızlı bir işlemci modu seçin.",

        # seçenekler
        "opt_lang": "Dil", "opt_quality": "Doğruluk", "opt_speed": "İşlemci",
        "lang_auto": "Otomatik algıla",
        "q_standard": "Standart", "q_high": "Yüksek",
        "q_standard_desc": "Daha hızlı ve hafif; net, gürültüsüz kayıtlar için yeterli.",
        "q_high_desc": "Önerilen. Ders kayıtlarında belirgin şekilde daha az hata yapar.",
        "mode_quiet": "Sessiz", "mode_balanced": "Dengeli", "mode_fast": "Hızlı",
        "mode_quiet_desc": "İşlemcinin yaklaşık dörtte birini kullanır; bu sırada bilgisayar rahatça kullanılabilir.",
        "mode_balanced_desc": "İşlemcinin yaklaşık yarısını kullanır.",
        "mode_fast_desc": "İşlemcinin büyük kısmını kullanır; bu sürede bilgisayar yavaşlayabilir.",
        "timestamps": "Zaman damgaları",

        # yazıya dökme
        "transcribe": "Yazıya dök", "retranscribe": "Yeniden yazıya dök", "cancel": "İptal",
        "cancelling": "İptal ediliyor…",
        "step_model": "Model yükleniyor", "step_read": "Ses okunuyor", "step_transcribe": "Yazıya dökülüyor",
        "progress_fmt": "{done} / {total}", "eta_fmt": "~{t} kaldı", "eta_calc": "süre hesaplanıyor…",
        "done_fmt": "Tamamlandı · {t} sürdü", "cancelled": "İptal edildi.", "error": "Hata oluştu.",
        "detected_lang": "Algılanan dil: {v}",
        "downloading_model": "Model ilk kez indiriliyor (bir kerelik, internet gerekir)…",
        "replace_q": "Mevcut metin yenisiyle değiştirilecek. Devam edilsin mi?",

        # transkript
        "transcript": "Transkript", "words_fmt": "{n} kelime",
        "copy": "Kopyala", "copied": "Kopyalandı", "save_txt": "Metni kaydet…",
        "placeholder_live": "Konuşulanlar burada canlı olarak belirir.",
        "placeholder_none": "Bu kaydın henüz transkripti yok.",
        "placeholder_file": "Yazıya dökülen metin burada akarak belirir.",

        # eylemler
        "save": "Kaydet", "delete": "Sil", "remove": "Listeden kaldır", "show_in_folder": "Klasörde göster",
        "delete_q": "Bu kayıt ve transkripti kalıcı olarak silinsin mi?",
        "saved_in": "Kaydedildi · {path}",
        "save_dialog": "Kaydet", "filter_text": "Metin", "filter_audio": "Ses/Video", "filter_all": "Tüm dosyalar",
        "file_dialog": "Ses dosyası seç",
        "unsupported": "Bu dosya ses içermiyor gibi görünüyor: {name}",

        # ayarlar
        "set_ui_lang": "Arayüz dili", "set_theme": "Görünüm", "set_folder": "Kayıt klasörü",
        "change": "Değiştir…", "open": "Aç", "folder_dialog": "Kayıt klasörünü seçin", "close": "Kapat",

        # çıkış / hata
        "quit_title": "Çıkış", "quit_body": "Devam eden bir işlem var. Çıkılsın mı?",
        "quit_unsaved": "{n} kayıt henüz kaydedilmedi.\n\nSaklarsanız bir sonraki açılışta listede olurlar.",
        "quit_keep": "Sakla ve çık", "quit_delete": "Sil ve çık", "error_title": "Hata",
        # gelişmiş
        "adv_title": "Gelişmiş", "adv_enable": "Gelişmiş mod (mühendisler için)",
        "adv_hint": "Canlı önizleme ayarlarını ve kayıt sayfalarında 'Sinyal analizi' ekranını açar.",
        "adv_live": "Canlı önizleme", "adv_draft_model": "Önizleme modeli",
        "dm_tiny": "Tiny — en hızlı", "dm_base": "Base — dengeli", "dm_small": "Small — en doğru",
        "adv_interval": "Yenileme aralığı", "adv_threads": "Önizleme iş parçacığı",
        "adv_silence": "Kesinleştirme duraklaması", "adv_min_chunk": "En kısa parça", "adv_max_chunk": "En uzun parça",
        "adv_beam": "Arama genişliği (beam)", "adv_defaults": "Varsayılanlar", "unit_s": " sn",
        "analysis": "Sinyal analizi",
        # analiz ekranı
        "an_title": "Sinyal analizi — {name}", "an_hover": "{t} s · {f} Hz · {db} {unit}",
        "an_segment": "Bölüm", "an_start": "Başlangıç", "an_length": "Süre",
        "an_method": "Yöntem", "an_transform": "Dönüşüm", "tf_stft": "Pencereli Fourier (STFT)", "tf_cwt": "Dalgacık (CWT)",
        "an_window": "Pencere", "win_hann": "Hann", "win_hamming": "Hamming", "win_blackman": "Blackman",
        "win_gauss": "Gauss", "win_rect": "Dikdörtgen", "an_nfft": "Pencere uzunluğu", "an_overlap": "Örtüşme",
        "an_wavelet": "Dalgacık", "wl_morlet": "Morlet", "wl_mexhat": "Meksika şapkası", "wl_paul": "Paul",
        "an_scales": "Ölçek sayısı",
        "an_display": "Gösterim", "an_faxis": "Frekans ekseni", "fa_linear": "Doğrusal", "fa_log": "Logaritmik",
        "fa_mel": "Mel", "an_range": "Dinamik aralık", "an_cmap": "Renk haritası",
        "cm_magma": "Magma", "cm_viridis": "Viridis", "cm_gray": "Gri",
        "an_processing": "İşleme", "an_denoise": "Gürültüyü ayıkla", "an_strength": "Güç",
        "an_boost": "Konuşmayı yükselt", "an_gain": "Kazanç", "an_trim": "Sessiz kısımları çıkar", "an_thresh": "Eşik",
        "an_compute": "Hesapla", "an_computing": "Hesaplanıyor…",
        "an_before": "Önce (orijinal)", "an_after": "Sonra (işlenmiş)", "an_diff": "Fark (önce − sonra)",
        "an_no_proc": "işleme seçilmedi", "an_ms": "{ms} ms", "an_nr": "gürültü ≈ {db} dB azaldı",
        "an_removed": "{s} sn sessizlik çıkarıldı",
        "an_play_orig": "Orijinal", "an_play_proc": "İşlenmiş (yeniden sentez)",
        "an_export": "İşlenmiş sesi kaydet…", "an_to_list": "İşlenmiş sesi listeye ekle",
        "an_exporting": "Kaydın tamamı işleniyor… %{p}", "an_processed_suffix": "(işlenmiş)",
    },
    "en": {
        "app_title": "Lecture Transcriber",
        "offline": "Works offline",
        "months": "January,February,March,April,May,June,July,August,September,October,November,December",
        "theme_system": "System", "theme_light": "Light", "theme_dark": "Dark",

        "add_tip": "New recording or audio file",
        "new_recording": "New recording", "add_file": "Add audio file…",
        "settings": "Settings",
        "rec_title": "Recording {n}",
        "rec_busy": "Another recording is in progress. The microphone can only be used by one recording at a time; finish it first.",
        "badge_unsaved": "Not saved", "badge_new": "New",
        "empty_title": "No recordings yet",
        "empty_hint": "Start a new recording or add an audio file.\nYou can also drop files onto the window.",

        "rec_ready": "Press the red button to start",
        "st_recording": "Recording", "st_paused": "Paused",
        "st_loading": "Getting ready…  audio is already being recorded",
        "st_finishing": "Processing the last part…",
        "rec_start_tip": "Start recording  (Ctrl+R)", "rec_stop_tip": "Finish recording  (Ctrl+R)",
        "pause_tip": "Pause", "resume_tip": "Resume", "play_tip": "Play",
        "live_text": "Live transcription",
        "live_text_on": "Speech appears on screen within ~2 s.",
        "live_text_off": "Only audio is recorded; almost no CPU is used. Transcribe it afterwards.",
        "options": "Options", "mic": "Microphone", "no_mic": "No microphone found",
        "mic_denied": "Microphone access was denied. Allow it in System Settings › Privacy & Security › Microphone.",
        "mic_error": "Could not open the microphone.",
        "lag_fmt": "Delay ~{s} s",
        "lag_warn": "The CPU can't keep up: choose 'Standard' accuracy or a faster CPU mode.",

        "opt_lang": "Language", "opt_quality": "Accuracy", "opt_speed": "CPU",
        "lang_auto": "Detect automatically",
        "q_standard": "Standard", "q_high": "High",
        "q_standard_desc": "Faster and lighter; good enough for clear, quiet recordings.",
        "q_high_desc": "Recommended. Makes noticeably fewer mistakes on lecture recordings.",
        "mode_quiet": "Quiet", "mode_balanced": "Balanced", "mode_fast": "Fast",
        "mode_quiet_desc": "Uses about a quarter of the CPU; the computer stays fully usable.",
        "mode_balanced_desc": "Uses about half of the CPU.",
        "mode_fast_desc": "Uses most of the CPU; the computer may feel slow meanwhile.",
        "timestamps": "Timestamps",

        "transcribe": "Transcribe", "retranscribe": "Transcribe again", "cancel": "Cancel",
        "cancelling": "Cancelling…",
        "step_model": "Loading model", "step_read": "Reading audio", "step_transcribe": "Transcribing",
        "progress_fmt": "{done} / {total}", "eta_fmt": "~{t} left", "eta_calc": "estimating…",
        "done_fmt": "Done · took {t}", "cancelled": "Cancelled.", "error": "An error occurred.",
        "detected_lang": "Detected language: {v}",
        "downloading_model": "Downloading the model for the first time (one-off, needs internet)…",
        "replace_q": "The current text will be replaced. Continue?",

        "transcript": "Transcript", "words_fmt": "{n} words",
        "copy": "Copy", "copied": "Copied", "save_txt": "Save text…",
        "placeholder_live": "Speech appears here live.",
        "placeholder_none": "This recording has no transcript yet.",
        "placeholder_file": "The transcript appears here as it is produced.",

        "save": "Save", "delete": "Delete", "remove": "Remove from list", "show_in_folder": "Show in folder",
        "delete_q": "Permanently delete this recording and its transcript?",
        "saved_in": "Saved · {path}",
        "save_dialog": "Save", "filter_text": "Text", "filter_audio": "Audio/Video", "filter_all": "All files",
        "file_dialog": "Choose an audio file",
        "unsupported": "This file doesn't seem to contain audio: {name}",

        "set_ui_lang": "Interface language", "set_theme": "Appearance", "set_folder": "Recordings folder",
        "change": "Change…", "open": "Open", "folder_dialog": "Choose the recordings folder", "close": "Close",

        "quit_title": "Quit", "quit_body": "A task is still running. Quit anyway?",
        "quit_unsaved": "{n} recording(s) are not saved yet.\n\nIf you keep them, they will be listed again next time.",
        "quit_keep": "Keep and quit", "quit_delete": "Delete and quit", "error_title": "Error",
        "adv_title": "Advanced", "adv_enable": "Advanced mode (for engineers)",
        "adv_hint": "Unlocks live preview tuning and the 'Signal analysis' screen on recording pages.",
        "adv_live": "Live preview", "adv_draft_model": "Preview model",
        "dm_tiny": "Tiny — fastest", "dm_base": "Base — balanced", "dm_small": "Small — most accurate",
        "adv_interval": "Refresh interval", "adv_threads": "Preview threads",
        "adv_silence": "Finalising pause", "adv_min_chunk": "Shortest part", "adv_max_chunk": "Longest part",
        "adv_beam": "Search width (beam)", "adv_defaults": "Defaults", "unit_s": " s",
        "analysis": "Signal analysis",
        "an_title": "Signal analysis — {name}", "an_hover": "{t} s · {f} Hz · {db} {unit}",
        "an_segment": "Segment", "an_start": "Start", "an_length": "Length",
        "an_method": "Method", "an_transform": "Transform", "tf_stft": "Windowed Fourier (STFT)", "tf_cwt": "Wavelet (CWT)",
        "an_window": "Window", "win_hann": "Hann", "win_hamming": "Hamming", "win_blackman": "Blackman",
        "win_gauss": "Gaussian", "win_rect": "Rectangular", "an_nfft": "Window length", "an_overlap": "Overlap",
        "an_wavelet": "Wavelet", "wl_morlet": "Morlet", "wl_mexhat": "Mexican hat", "wl_paul": "Paul",
        "an_scales": "Number of scales",
        "an_display": "Display", "an_faxis": "Frequency axis", "fa_linear": "Linear", "fa_log": "Logarithmic",
        "fa_mel": "Mel", "an_range": "Dynamic range", "an_cmap": "Colour map",
        "cm_magma": "Magma", "cm_viridis": "Viridis", "cm_gray": "Grey",
        "an_processing": "Processing", "an_denoise": "Remove noise", "an_strength": "Strength",
        "an_boost": "Boost speech", "an_gain": "Gain", "an_trim": "Remove silent parts", "an_thresh": "Threshold",
        "an_compute": "Compute", "an_computing": "Computing…",
        "an_before": "Before (original)", "an_after": "After (processed)", "an_diff": "Difference (before − after)",
        "an_no_proc": "no processing selected", "an_ms": "{ms} ms", "an_nr": "noise reduced by ≈ {db} dB",
        "an_removed": "{s} s of silence removed",
        "an_play_orig": "Original", "an_play_proc": "Processed (resynthesised)",
        "an_export": "Save processed audio…", "an_to_list": "Add processed audio to list",
        "an_exporting": "Processing the whole recording… {p}%", "an_processed_suffix": "(processed)",
    },
    "de": {
        "app_title": "Vorlesungs-Transkript",
        "offline": "Funktioniert offline",
        "months": "Januar,Februar,März,April,Mai,Juni,Juli,August,September,Oktober,November,Dezember",
        "theme_system": "System", "theme_light": "Hell", "theme_dark": "Dunkel",

        "add_tip": "Neue Aufnahme oder Audiodatei",
        "new_recording": "Neue Aufnahme", "add_file": "Audiodatei hinzufügen…",
        "settings": "Einstellungen",
        "rec_title": "Aufnahme {n}",
        "rec_busy": "Es läuft bereits eine andere Aufnahme. Das Mikrofon kann nur von einer Aufnahme gleichzeitig genutzt werden; beenden Sie sie zuerst.",
        "badge_unsaved": "Nicht gespeichert", "badge_new": "Neu",
        "empty_title": "Noch keine Aufnahmen",
        "empty_hint": "Starten Sie eine neue Aufnahme oder fügen Sie eine Audiodatei hinzu.\nDateien können auch ins Fenster gezogen werden.",

        "rec_ready": "Zum Starten den roten Knopf drücken",
        "st_recording": "Aufnahme läuft", "st_paused": "Pausiert",
        "st_loading": "Wird vorbereitet…  Ton wird bereits aufgenommen",
        "st_finishing": "Letzter Teil wird verarbeitet…",
        "rec_start_tip": "Aufnahme starten  (Strg+R)", "rec_stop_tip": "Aufnahme beenden  (Strg+R)",
        "pause_tip": "Pause", "resume_tip": "Fortsetzen", "play_tip": "Abspielen",
        "live_text": "Live-Mitschrift",
        "live_text_on": "Das Gesprochene erscheint nach ~2 s auf dem Bildschirm.",
        "live_text_off": "Nur Ton wird aufgenommen; kaum CPU-Last. Später mit 'Transkribieren' umwandeln.",
        "options": "Optionen", "mic": "Mikrofon", "no_mic": "Kein Mikrofon gefunden",
        "mic_denied": "Mikrofonzugriff verweigert. In Systemeinstellungen › Datenschutz & Sicherheit › Mikrofon erlauben.",
        "mic_error": "Mikrofon konnte nicht geöffnet werden.",
        "lag_fmt": "Verzögerung ~{s} s",
        "lag_warn": "Die CPU kommt nicht hinterher: 'Standard'-Genauigkeit oder schnelleren CPU-Modus wählen.",

        "opt_lang": "Sprache", "opt_quality": "Genauigkeit", "opt_speed": "CPU",
        "lang_auto": "Automatisch erkennen",
        "q_standard": "Standard", "q_high": "Hoch",
        "q_standard_desc": "Schneller und leichter; reicht für klare, ruhige Aufnahmen.",
        "q_high_desc": "Empfohlen. Macht bei Vorlesungsaufnahmen deutlich weniger Fehler.",
        "mode_quiet": "Leise", "mode_balanced": "Ausgewogen", "mode_fast": "Schnell",
        "mode_quiet_desc": "Nutzt etwa ein Viertel der CPU; der Rechner bleibt voll nutzbar.",
        "mode_balanced_desc": "Nutzt etwa die Hälfte der CPU.",
        "mode_fast_desc": "Nutzt den Großteil der CPU; der Rechner kann langsamer werden.",
        "timestamps": "Zeitstempel",

        "transcribe": "Transkribieren", "retranscribe": "Erneut transkribieren", "cancel": "Abbrechen",
        "cancelling": "Wird abgebrochen…",
        "step_model": "Modell wird geladen", "step_read": "Audio wird gelesen", "step_transcribe": "Wird transkribiert",
        "progress_fmt": "{done} / {total}", "eta_fmt": "noch ~{t}", "eta_calc": "wird berechnet…",
        "done_fmt": "Fertig · Dauer {t}", "cancelled": "Abgebrochen.", "error": "Ein Fehler ist aufgetreten.",
        "detected_lang": "Erkannte Sprache: {v}",
        "downloading_model": "Modell wird erstmalig heruntergeladen (einmalig, Internet nötig)…",
        "replace_q": "Der vorhandene Text wird ersetzt. Fortfahren?",

        "transcript": "Transkript", "words_fmt": "{n} Wörter",
        "copy": "Kopieren", "copied": "Kopiert", "save_txt": "Text speichern…",
        "placeholder_live": "Das Gesprochene erscheint hier live.",
        "placeholder_none": "Für diese Aufnahme gibt es noch kein Transkript.",
        "placeholder_file": "Das Transkript erscheint hier während der Verarbeitung.",

        "save": "Speichern", "delete": "Löschen", "remove": "Aus Liste entfernen", "show_in_folder": "Im Ordner zeigen",
        "delete_q": "Diese Aufnahme samt Transkript endgültig löschen?",
        "saved_in": "Gespeichert · {path}",
        "save_dialog": "Speichern", "filter_text": "Text", "filter_audio": "Audio/Video", "filter_all": "Alle Dateien",
        "file_dialog": "Audiodatei wählen",
        "unsupported": "Diese Datei scheint keinen Ton zu enthalten: {name}",

        "set_ui_lang": "Sprache der Oberfläche", "set_theme": "Erscheinungsbild", "set_folder": "Aufnahmeordner",
        "change": "Ändern…", "open": "Öffnen", "folder_dialog": "Aufnahmeordner wählen", "close": "Schließen",

        "quit_title": "Beenden", "quit_body": "Es läuft noch ein Vorgang. Trotzdem beenden?",
        "quit_unsaved": "{n} Aufnahme(n) sind noch nicht gespeichert.\n\nBehalten Sie sie, erscheinen sie beim nächsten Start wieder.",
        "quit_keep": "Behalten und beenden", "quit_delete": "Löschen und beenden", "error_title": "Fehler",
        "adv_title": "Erweitert", "adv_enable": "Erweiterter Modus (für Ingenieure)",
        "adv_hint": "Schaltet die Feinabstimmung der Live-Vorschau und die 'Signalanalyse' auf Aufnahmeseiten frei.",
        "adv_live": "Live-Vorschau", "adv_draft_model": "Vorschaumodell",
        "dm_tiny": "Tiny — am schnellsten", "dm_base": "Base — ausgewogen", "dm_small": "Small — am genauesten",
        "adv_interval": "Aktualisierungsintervall", "adv_threads": "Vorschau-Threads",
        "adv_silence": "Pause zum Finalisieren", "adv_min_chunk": "Kürzester Teil", "adv_max_chunk": "Längster Teil",
        "adv_beam": "Suchbreite (Beam)", "adv_defaults": "Standardwerte", "unit_s": " s",
        "analysis": "Signalanalyse",
        "an_title": "Signalanalyse — {name}", "an_hover": "{t} s · {f} Hz · {db} {unit}",
        "an_segment": "Abschnitt", "an_start": "Beginn", "an_length": "Länge",
        "an_method": "Methode", "an_transform": "Transformation", "tf_stft": "Gefensterte Fourier (STFT)", "tf_cwt": "Wavelet (CWT)",
        "an_window": "Fenster", "win_hann": "Hann", "win_hamming": "Hamming", "win_blackman": "Blackman",
        "win_gauss": "Gauß", "win_rect": "Rechteck", "an_nfft": "Fensterlänge", "an_overlap": "Überlappung",
        "an_wavelet": "Wavelet", "wl_morlet": "Morlet", "wl_mexhat": "Mexikanischer Hut", "wl_paul": "Paul",
        "an_scales": "Anzahl Skalen",
        "an_display": "Darstellung", "an_faxis": "Frequenzachse", "fa_linear": "Linear", "fa_log": "Logarithmisch",
        "fa_mel": "Mel", "an_range": "Dynamikbereich", "an_cmap": "Farbskala",
        "cm_magma": "Magma", "cm_viridis": "Viridis", "cm_gray": "Grau",
        "an_processing": "Verarbeitung", "an_denoise": "Rauschen entfernen", "an_strength": "Stärke",
        "an_boost": "Sprache anheben", "an_gain": "Verstärkung", "an_trim": "Stille Teile entfernen", "an_thresh": "Schwelle",
        "an_compute": "Berechnen", "an_computing": "Wird berechnet…",
        "an_before": "Vorher (original)", "an_after": "Nachher (verarbeitet)", "an_diff": "Differenz (vorher − nachher)",
        "an_no_proc": "keine Verarbeitung gewählt", "an_ms": "{ms} ms", "an_nr": "Rauschen um ≈ {db} dB reduziert",
        "an_removed": "{s} s Stille entfernt",
        "an_play_orig": "Original", "an_play_proc": "Verarbeitet (resynthetisiert)",
        "an_export": "Verarbeiteten Ton speichern…", "an_to_list": "Verarbeiteten Ton zur Liste hinzufügen",
        "an_exporting": "Gesamte Aufnahme wird verarbeitet… {p} %", "an_processed_suffix": "(verarbeitet)",
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


def fmt_date(dt):
    """'2 Ekim 2026, 08:14' — ay adı arayüz diline göre."""
    month = tr("months").split(",")[dt.month - 1]
    if _lang == "en":
        return f"{month} {dt.day}, {dt.year}, {dt:%H:%M}"
    if _lang == "de":
        return f"{dt.day}. {month} {dt.year}, {dt:%H:%M}"
    return f"{dt.day} {month} {dt.year}, {dt:%H:%M}"
