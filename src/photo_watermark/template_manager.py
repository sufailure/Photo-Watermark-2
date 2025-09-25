import json
from pathlib import Path
from typing import List, Optional

from .settings import Template, WatermarkSettings, ExportSettings


class TemplateManager:
    """Persist and manage watermark templates on disk."""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        base_dir = storage_dir or Path.home() / ".photo_watermark"
        base_dir.mkdir(parents=True, exist_ok=True)
        self._storage_path = base_dir / "templates.json"
        self._data = {
            "templates": [],
            "last_template": None,
            "last_settings": {
                "watermark": WatermarkSettings().to_dict(),
                "export": ExportSettings().to_dict(),
            },
        }
        self._load()

    def _load(self) -> None:
        if self._storage_path.exists():
            try:
                content = json.loads(self._storage_path.read_text(encoding="utf-8"))
                if isinstance(content, dict):
                    self._data.update(content)
            except json.JSONDecodeError:
                pass
        if not self._data["templates"]:
            default_template = Template(
                name="Default",
                watermark=WatermarkSettings(),
                export=ExportSettings(),
            )
            self._data["templates"].append(default_template.to_dict())
            self._data["last_template"] = default_template.name
            self._flush()

    def _flush(self) -> None:
        self._storage_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def list_templates(self) -> List[Template]:
        return [Template.from_dict(t) for t in self._data.get("templates", [])]

    def get_template(self, name: str) -> Optional[Template]:
        for tpl in self._data.get("templates", []):
            if tpl.get("name") == name:
                return Template.from_dict(tpl)
        return None

    def save_template(self, template: Template) -> None:
        templates = self._data.setdefault("templates", [])
        for idx, tpl in enumerate(templates):
            if tpl.get("name") == template.name:
                templates[idx] = template.to_dict()
                break
        else:
            templates.append(template.to_dict())
        self._data["last_template"] = template.name
        self._data["last_settings"] = {
            "watermark": template.watermark.to_dict(),
            "export": template.export.to_dict(),
        }
        self._flush()

    def delete_template(self, name: str) -> bool:
        templates = self._data.get("templates", [])
        new_templates = [tpl for tpl in templates if tpl.get("name") != name]
        if len(new_templates) == len(templates):
            return False
        self._data["templates"] = new_templates
        if self._data.get("last_template") == name:
            self._data["last_template"] = new_templates[0]["name"] if new_templates else None
        self._flush()
        return True

    def get_last_template_name(self) -> Optional[str]:
        return self._data.get("last_template")

    def get_last_settings(self) -> Template:
        watermark = WatermarkSettings.from_dict(self._data.get("last_settings", {}).get("watermark", {}))
        export = ExportSettings.from_dict(self._data.get("last_settings", {}).get("export", {}))
        name = self._data.get("last_template") or "Last Used"
        return Template(name=name, watermark=watermark, export=export)

    def record_last_settings(
        self,
        watermark: WatermarkSettings,
        export: ExportSettings,
        template_name: Optional[str] = None,
    ) -> None:
        self._data["last_settings"] = {
            "watermark": watermark.to_dict(),
            "export": export.to_dict(),
        }
        if template_name:
            self._data["last_template"] = template_name
        self._flush()
