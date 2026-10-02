"""Yeni sürüm bildirimi: açılışta GitHub'daki son sürümün numarasına bakar (başka hiçbir veri gönderilmez).

Yeni sürüm varsa kullanıcıya sorar; "İndir" indirme sayfasını tarayıcıda açar. Güvenlik için bilerek
sınırlı: hiçbir dosya indirilmez ya da çalıştırılmaz, uygulama kendini değiştirmez; cevaptan yalnızca
sürüm numarası okunur ve açılan adres her zaman koddaki sabit PAGE'dir (cevaptaki bir bağlantı değil).
İnternet yoksa ya da bir hata olursa sessizce geçer. Ayarlar'dan kapatılabilir.
Ağ isteği Qt ile yapılır: her sistemin kendi sertifika deposunu kullanır (paketlenmiş Python'un
macOS'taki sertifika sorunu olmaz).
"""
import json

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from version import REPO, VERSION

API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"


def parse(tag):
    """'v1.2.3' -> (1, 2, 3); sürüm numarası değilse None."""
    try:
        return tuple(int(x) for x in str(tag).lstrip("vV").split("."))
    except ValueError:
        return None


def is_newer(tag, current=VERSION):
    new, cur = parse(tag), parse(current)
    return new is not None and cur is not None and new > cur


class UpdateChecker(QObject):
    """found(etiket) yalnızca daha yeni bir sürüm varsa yayılır. done(http durumu | None) her zaman."""
    found = pyqtSignal(str)
    done = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.net = QNetworkAccessManager(self)

    def check(self):
        req = QNetworkRequest(QUrl(API))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", f"DersTranskript/{VERSION}".encode())
        req.setTransferTimeout(8000)
        reply = self.net.get(req)
        reply.finished.connect(lambda: self._on_reply(reply))

    def _on_reply(self, reply):
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
                tag = str(data.get("tag_name", ""))[:20]
                if is_newer(tag):
                    self.found.emit(tag)
        except (ValueError, AttributeError):
            pass
        finally:
            reply.deleteLater()
            self.done.emit(status)
