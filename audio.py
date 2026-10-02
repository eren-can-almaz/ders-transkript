"""Mikrofon girişi: Qt'nin ses modülüyle okur, 16 kHz mono float32'ye çevirir."""
import numpy as np
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSource

from core import SR
from i18n import tr


class Microphone:
    """Seçili mikrofondan sesi okur, 16 kHz mono float32'ye çevirip `on_audio`'ya verir."""
    _DTYPES = {
        QAudioFormat.SampleFormat.UInt8: (np.uint8, lambda a: (a.astype(np.float32) - 128) / 128),
        QAudioFormat.SampleFormat.Int16: (np.int16, lambda a: a.astype(np.float32) / 32768),
        QAudioFormat.SampleFormat.Int32: (np.int32, lambda a: a.astype(np.float32) / 2147483648),
        QAudioFormat.SampleFormat.Float: (np.float32, lambda a: a),
    }

    def __init__(self, device, on_audio, parent):
        fmt = QAudioFormat()
        fmt.setSampleRate(SR)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()  # cihaz desteklemiyorsa kendi formatında al, sonra dönüştür
        self.fmt = fmt
        self.dtype, self.to_float = self._DTYPES.get(fmt.sampleFormat(), self._DTYPES[QAudioFormat.SampleFormat.Int16])
        self.frame_bytes = fmt.bytesPerFrame()
        self.on_audio = on_audio
        self.rest = b""
        self.source = QAudioSource(device, fmt, parent)
        self.source.setBufferSize(fmt.bytesForDuration(200_000))  # ~200 ms
        self.io = self.source.start()
        if self.io is None or self.source.error() != QAudio.Error.NoError:
            raise RuntimeError(tr("mic_error"))
        self.io.readyRead.connect(self._read)

    def _read(self):
        data = self.rest + bytes(self.io.readAll())
        usable = len(data) - len(data) % self.frame_bytes
        self.rest = data[usable:]
        if not usable:
            return
        a = self.to_float(np.frombuffer(data[:usable], self.dtype))
        ch = self.fmt.channelCount()
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        rate = self.fmt.sampleRate()
        if rate != SR:
            n = int(round(len(a) * SR / rate))
            a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
        self.on_audio(a)

    def stop(self):
        self.source.stop()
