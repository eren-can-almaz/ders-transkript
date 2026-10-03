"""Yeni sürüm bildirimi: açılışta GitHub'daki son sürümün numarasına bakar (başka hiçbir veri gönderilmez).

Yeni sürüm varsa kullanıcıya sorar; "İndir" indirme sayfasını tarayıcıda açar. Güvenlik için bilerek
sınırlı: hiçbir dosya indirilmez ya da çalıştırılmaz, uygulama kendini değiştirmez; cevaptan yalnızca
sürüm numarası okunur. Açılan adres, cevap deponun kendi sürüm sayfasını gösteriyorsa odur (kullanıcı adı
değişse de doğru adres), değilse koddaki sabit PAGE.
İnternet yoksa ya da bir hata olursa sessizce geçer. Ayarlar'dan kapatılabilir.
Ağ isteği Qt ile yapılır: her sistemin kendi sertifika deposunu kullanır (paketlenmiş Python'un
macOS'taki sertifika sorunu olmaz).
"""
import json

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from version import REPO, REPO_ID, VERSION

API = f"https://api.github.com/repositories/{REPO_ID}/releases/latest"  # adla değil kimlikle
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


def safe_page(url):
    """Cevaptaki sürüm sayfası yalnızca github.com'da bir sürüm sayfasıysa kullanılır; değilse sabit PAGE."""
    from urllib.parse import urlparse
    try:
        u = urlparse(str(url))
    except ValueError:
        return PAGE
    parts = u.path.strip("/").split("/")
    ok = (u.scheme == "https" and u.netloc == "github.com" and len(parts) == 5
          and parts[1] == REPO.split("/")[1] and parts[2:4] == ["releases", "tag"] and not u.query and not u.fragment)
    return url if ok else PAGE


class UpdateChecker(QObject):
    """found(etiket, sayfa) yalnızca daha yeni bir sürüm varsa yayılır. done(http durumu | None) her zaman."""
    found = pyqtSignal(str, str)
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
                    self.found.emit(tag, safe_page(data.get("html_url")))
        except (ValueError, AttributeError):
            pass
        finally:
            reply.deleteLater()
            self.done.emit(status)
