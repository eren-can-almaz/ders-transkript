"""Kayıt kütüphanesi: listedeki öğeler (mikrofon kayıtları ve eklenen ses dosyaları) ve kalıcılığı.

- Kaydedilmemiş mikrofon kayıtlarının sesi `<veri>/unsaved/` altında durur; Kaydet ile seçilen
  yere taşınır, Sil ile silinir.
- Her öğenin transkripti `<veri>/texts/<id>.txt` içinde tutulur; liste `<veri>/library.json`.
- Program çökerse, listede olmayan geçici ses dosyaları bir sonraki açılışta kayıt olarak geri gelir.
"""
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from core import probe_audio, user_data_dir

AUDIO_SUFFIXES = (".m4a", ".wav")


def unsaved_dir() -> Path:
    d = user_data_dir() / "unsaved"
    d.mkdir(parents=True, exist_ok=True)
    return d


def texts_dir() -> Path:
    d = user_data_dir() / "texts"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Item:
    """Listede bir öğe. kind: 'rec' (mikrofon kaydı) | 'file' (eklenen ses dosyası)."""

    def __init__(self, kind, title, audio=None, created=None, duration=None, saved=False, id=None):
        self.id = id or uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.audio = Path(audio) if audio else None
        self.created = created or datetime.now()
        self.duration = duration
        self.saved = saved            # rec: kalıcı klasöre kaydedildi mi (file her zaman True)
        self.text = ""
        self.new = False              # rec: henüz başlatılmadı (listeye yazılmaz)

    @property
    def text_path(self):
        return texts_dir() / f"{self.id}.txt"

    def to_json(self):
        return {"id": self.id, "kind": self.kind, "title": self.title,
                "audio": str(self.audio) if self.audio else None,
                "created": self.created.isoformat(timespec="seconds"),
                "duration": self.duration, "saved": self.saved}

    @classmethod
    def from_json(cls, d):
        it = cls(d["kind"], d["title"], d.get("audio"), datetime.fromisoformat(d["created"]),
                 d.get("duration"), d.get("saved", False), d["id"])
        if it.text_path.exists():
            it.text = it.text_path.read_text(encoding="utf-8")
        return it


class Library:
    def __init__(self):
        self.path = user_data_dir() / "library.json"
        self.items = []
        self._load()

    # --- kalıcılık ------------------------------------------------------
    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for d in data.get("items", []):
            try:
                it = Item.from_json(d)
            except (KeyError, ValueError):
                continue
            if it.audio and not it.audio.exists() and not it.text.strip():
                continue  # dosyası silinmiş ve metni de yok: listeden düş
            self.items.append(it)
        # listede olmayan geçici kayıtlar (çökme veya önceki sürüm): kayıt olarak geri getir
        known = {it.audio for it in self.items if it.audio}
        for p in sorted(unsaved_dir().iterdir()):
            if p.suffix in AUDIO_SUFFIXES and p not in known:
                when = datetime.fromtimestamp(p.stat().st_mtime)
                it = Item("rec", self.next_rec_title(when), p, when, probe_audio(str(p))[0])
                old_txt = p.with_suffix(".txt")
                if old_txt.exists():
                    it.text = old_txt.read_text(encoding="utf-8")
                    self.write_text(it)
                    old_txt.unlink()
                self.items.append(it)
        self.items.sort(key=lambda i: i.created, reverse=True)
        self.save_index()

    def save_index(self):
        data = {"items": [it.to_json() for it in self.items if not it.new]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def write_text(self, it):
        if it.text.strip():
            it.text_path.write_text(it.text, encoding="utf-8")
        elif it.text_path.exists():
            it.text_path.unlink()

    # --- öğeler ---------------------------------------------------------
    def next_rec_title(self, when=None):
        """Gün bazlı numara: 'Kayıt N', N = o günün kayıtlarındaki en büyük numara + 1.

        Yalnızca aynı günün kayıtlarına bakılır; eski günlerin kayıtları numarayı etkilemez.
        Adı elle değiştirilmiş kayıtlar sayılmaz. Her arayüz dilindeki kalıp ('Kayıt 3',
        'Recording 3', 'Aufnahme 3') tanınır.
        """
        import re
        from i18n import STRINGS, tr
        day = (when or datetime.now()).date()
        patterns = [re.compile("^" + re.escape(lang["rec_title"]).replace(re.escape("{n}"), r"(\d+)") + "$")
                    for lang in STRINGS.values()]
        used = [0]
        for it in self.items:
            if it.kind == "rec" and it.created.date() == day:
                for pat in patterns:
                    m = pat.match(it.title)
                    if m:
                        used.append(int(m.group(1)))
        return tr("rec_title", n=max(used) + 1)

    def rename(self, it, name):
        """Adı değiştir. Kaydedilmiş kayıtta diskteki ses (ve .txt) dosyası da yeniden adlandırılır;
        eklenen ses dosyalarının (kullanıcının kendi dosyaları) diskteki adına dokunulmaz."""
        if it.kind == "rec" and it.saved and it.audio and it.audio.exists():
            safe = "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip()
            if safe and safe != it.audio.stem:
                dest = it.audio.with_name(safe + it.audio.suffix)
                if dest.exists():
                    raise FileExistsError(str(dest))
                old_txt = it.audio.with_suffix(".txt")
                it.audio.rename(dest)
                if old_txt.exists():
                    old_txt.rename(dest.with_suffix(".txt"))
                it.audio = dest
        it.title = name
        self.save_index()

    def add(self, it):
        self.items.insert(0, it)
        self.save_index()

    def unsaved(self):
        return [it for it in self.items if it.kind == "rec" and not it.saved and not it.new and it.audio]

    def remove(self, it, delete_files):
        """delete_files: kaydedilmemiş kaydın sesi de silinir. Kaydedilmiş/eklenmiş dosyalara dokunulmaz."""
        if delete_files and it.kind == "rec" and not it.saved and it.audio and it.audio.exists():
            it.audio.unlink()
        if it.text_path.exists():
            it.text_path.unlink()
        if it in self.items:
            self.items.remove(it)
        self.save_index()

    def save_recording(self, it, dest: Path):
        """Kaydı seçilen yere taşır; transkript varsa yanına aynı adla .txt yazar."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(it.audio), dest)
        it.audio = dest
        it.saved = True
        it.title = dest.stem
        if it.text.strip():
            dest.with_suffix(".txt").write_text(it.text, encoding="utf-8")
        self.save_index()
