from pathlib import Path
import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)
_src_package = Path(__file__).resolve().parent.parent / "src" / __name__
if _src_package.exists():
    __path__.append(str(_src_package))
