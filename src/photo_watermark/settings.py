from dataclasses import dataclass, field, asdict
from typing import Dict, Tuple


@dataclass
class WatermarkSettings:
    text: str = "Sample Watermark"
    font_family: str = "Arial"
    font_size: int = 48
    color: str = "#FFFFFF"
    opacity: int = 70  # 0-100
    position_ratio: Tuple[float, float] = (0.5, 0.5)  # relative to image size, top-left of text

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "WatermarkSettings":
        defaults = cls().to_dict()
        defaults.update(data or {})
        return cls(**defaults)


@dataclass
class ExportSettings:
    output_folder: str = ""
    output_format: str = "PNG"  # PNG or JPEG
    naming_mode: str = "suffix"  # original | prefix | suffix
    prefix: str = "wm_"
    suffix: str = "_watermarked"
    jpeg_quality: int = 90

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "ExportSettings":
        defaults = cls().to_dict()
        defaults.update(data or {})
        return cls(**defaults)


@dataclass
class Template:
    name: str
    watermark: WatermarkSettings = field(default_factory=WatermarkSettings)
    export: ExportSettings = field(default_factory=ExportSettings)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "watermark": self.watermark.to_dict(),
            "export": self.export.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Template":
        return cls(
            name=data.get("name", "Unnamed"),
            watermark=WatermarkSettings.from_dict(data.get("watermark", {})),
            export=ExportSettings.from_dict(data.get("export", {})),
        )
