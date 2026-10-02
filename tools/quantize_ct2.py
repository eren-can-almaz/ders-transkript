"""Whisper CTranslate2 model.bin dosyasını diskte int8'e çevirir: dosya boyutu yarıya iner, sonuç değişmez.

Uygulama modelleri zaten compute_type="int8" ile yükler; ctranslate2 bu durumda ağırlıkları yüklerken
satır başına ölçekle int8'e çevirir (specs/model_spec.py, _quantize ile aynı yöntem) ama Whisper'ın
conv katmanlarını float bırakır ("Conv1D only supports float types"). Burada da aynısı yapılır; conv
nicemlenirse çıktı bozulur. Doğrulama: kodlayıcı çıktısı ve üretilen belirteçler orijinalle birebir aynı.
PyTorch gerekmez.

Kullanım: python tools/quantize_ct2.py models/large-v3-turbo [models/small ...]
"""
import struct
import sys
from pathlib import Path

import numpy as np

DTYPES = {0: np.float32, 1: np.int8, 2: np.int16, 3: np.int32, 4: np.float16}  # 5: bfloat16


def _read_str(f):
    n, = struct.unpack("H", f.read(2))
    return f.read(n)[:-1].decode("utf-8")


def _write_str(f, s):
    b = s.encode("utf-8")
    f.write(struct.pack("H", len(b) + 1) + b + b"\0")


def quantize(model_dir: Path, skip=lambda name: "conv" in name):
    src = model_dir / "model.bin"
    tmp = model_dir / "model.bin.int8"
    with open(src, "rb") as f, open(tmp, "wb") as out:
        version, = struct.unpack("I", f.read(4))
        if version != 6:
            raise SystemExit(f"{src}: desteklenmeyen sürüm {version}")
        name = _read_str(f)
        revision, count = struct.unpack("II", f.read(8))
        variables = []
        for _ in range(count):
            vname = _read_str(f)
            rank, = struct.unpack("B", f.read(1))
            shape = struct.unpack(f"{rank}I", f.read(4 * rank))
            dtype, nbytes = struct.unpack("=BI", f.read(5))
            variables.append((vname, shape, dtype, f.read(nbytes)))
        aliases = [(_read_str(f), _read_str(f)) for _ in range(struct.unpack("I", f.read(4))[0])]
        names = {v[0] for v in variables}
        if any(n.endswith("weight_scale") for n in names):
            print(f"{model_dir}: zaten nicemlenmiş, atlandı")
            tmp.unlink()
            return

        result = []
        for vname, shape, dtype, data in variables:
            # Linear / Conv1D / Embeddings ağırlıkları "weight" adını taşır (LayerNorm: gamma/beta)
            if vname.endswith("/weight") and len(shape) in (2, 3) and dtype in (0, 4) and not skip(vname):
                w = np.frombuffer(data, DTYPES[dtype]).astype(np.float32).reshape(shape[0], -1)
                amax = np.abs(w).max(axis=1)
                amax[amax == 0] = 127.0
                scale = (127.0 / amax).astype(np.float32)
                q = np.rint(w * scale[:, None]).astype(np.int8)
                result.append((vname, shape, 1, q.tobytes()))
                result.append((vname + "_scale", (shape[0],), 0, scale.tobytes()))
            else:
                result.append((vname, shape, dtype, data))

        out.write(struct.pack("I", version))
        _write_str(out, name)
        out.write(struct.pack("II", revision, len(result)))
        for vname, shape, dtype, data in result:
            _write_str(out, vname)
            out.write(struct.pack("B", len(shape)) + struct.pack(f"{len(shape)}I", *shape))
            out.write(struct.pack("=BI", dtype, len(data)))
            out.write(data)
        out.write(struct.pack("I", len(aliases)))
        for a, b in aliases:
            _write_str(out, a)
            _write_str(out, b)
    before = src.stat().st_size
    tmp.replace(src)
    print(f"{model_dir}: {before / 1e6:.0f} MB -> {src.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    for d in sys.argv[1:]:
        quantize(Path(d))
