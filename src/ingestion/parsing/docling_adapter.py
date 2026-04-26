"""Docling adapter for file conversion and low-level item extraction."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


class DoclingAdapter:
    """Wrap Docling-specific conversion and document item access behavior."""

    def __init__(self, converter: Any | None = None) -> None:
        """Initialize adapter with explicit converter or default Docling converter."""
        self.converter = converter or self._build_docling_converter()

    def convert(self, path: Path) -> Any:
        """Run Docling conversion for path, including `.txt` fallback via markdown mode."""
        suffix = path.suffix.lower()
        if suffix == ".txt":
            raw_text = self._read_text_file(path)
            input_format = self._docling_input_format("MD")
            return self.converter.convert_string(
                content=raw_text,
                format=input_format,
                name=path.name,
            )
        return self.converter.convert(path, raises_on_error=True)

    def extract_item_text(self, item: Any, doc: Any) -> str:
        """Extract canonical text from a Docling item across item categories."""
        if hasattr(item, "caption_text"):
            try:
                caption = item.caption_text(doc)
                if caption:
                    return str(caption)
            except Exception:
                pass

        if hasattr(item, "text") and getattr(item, "text"):
            return str(getattr(item, "text"))
        if hasattr(item, "orig") and getattr(item, "orig"):
            return str(getattr(item, "orig"))
        if hasattr(item, "export_to_markdown"):
            try:
                return str(item.export_to_markdown(doc=doc))
            except TypeError:
                return str(item.export_to_markdown(doc))
            except Exception:
                return ""
        return ""

    def item_page(self, item: Any) -> int:
        """Return 1-based page number from item provenance when available."""
        provenance = getattr(item, "prov", None)
        if not provenance:
            return 1
        first = provenance[0]
        page_no = getattr(first, "page_no", None)
        if isinstance(page_no, int) and page_no > 0:
            return page_no
        return 1

    def table_rows(self, item: Any, doc: Any) -> list[list[str]]:
        """Convert a Docling table item into row/column text representation."""
        try:
            dataframe = item.export_to_dataframe(doc=doc)
        except Exception:
            return self._rows_from_table_text(item.export_to_markdown(doc=doc))

        rows: list[list[str]] = []
        for _, series in dataframe.fillna("").iterrows():
            row = [str(cell).strip() for cell in series.tolist()]
            if any(cell for cell in row):
                rows.append(row)
        return rows

    def item_bboxes(self, item: Any) -> list[dict[str, Any]]:
        """Extract normalized bbox descriptors from Docling provenance."""
        provenance = getattr(item, "prov", None)
        if not provenance:
            return []

        boxes: list[dict[str, Any]] = []
        for prov in provenance:
            page_no = getattr(prov, "page_no", None)
            bbox = getattr(prov, "bbox", None)
            if bbox is None:
                continue

            left = self._coord_value(bbox, "l", "left", "x0", "x_min")
            t = self._coord_value(bbox, "t", "top", "y0", "y_min")
            r = self._coord_value(bbox, "r", "right", "x1", "x_max")
            b = self._coord_value(bbox, "b", "bottom", "y1", "y_max")
            if None in {left, t, r, b}:
                continue
            assert left is not None and t is not None and r is not None and b is not None
            left_value = float(left)
            top_value = float(t)
            right_value = float(r)
            bottom_value = float(b)

            coord_origin = getattr(bbox, "coord_origin", None) or getattr(
                prov, "coord_origin", None
            )
            origin_str = str(coord_origin).lower() if coord_origin is not None else "unknown"
            boxes.append(
                {
                    "page": int(page_no) if isinstance(page_no, int) and page_no > 0 else 1,
                    "l": left_value,
                    "t": top_value,
                    "r": right_value,
                    "b": bottom_value,
                    "origin": origin_str,
                }
            )
        return boxes

    @staticmethod
    def item_types() -> dict[str, Any]:
        """Return Docling node item classes used for semantic mapping."""
        from docling_core.types.doc.document import (
            FormulaItem,
            PictureItem,
            SectionHeaderItem,
            TableItem,
            TextItem,
            TitleItem,
        )

        return {
            "SectionHeaderItem": SectionHeaderItem,
            "TitleItem": TitleItem,
            "TextItem": TextItem,
            "FormulaItem": FormulaItem,
            "TableItem": TableItem,
            "PictureItem": PictureItem,
        }

    @staticmethod
    def is_successful_conversion(status: Any) -> bool:
        """Return true when Docling conversion status indicates successful output."""
        status_str = str(status).lower()
        return status_str.endswith("success")

    @staticmethod
    def _read_text_file(path: Path) -> str:
        """Read text file content using robust fallback encodings."""
        for encoding in ("utf-8", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _docling_input_format(name: str) -> Any:
        """Resolve an `InputFormat` enum entry from Docling by symbolic name."""
        from docling.datamodel.base_models import InputFormat

        return getattr(InputFormat, name)

    @staticmethod
    def _build_docling_converter() -> Any:
        """Create default Docling converter with clear dependency error message."""
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise ImportError(
                "Docling is required for parsing. Install dependencies from requirements/base.txt."
            ) from exc
        artifacts_path = os.environ.get("DOCLING_ARTIFACTS_PATH")
        if artifacts_path:
            DoclingAdapter._ensure_rapidocr_models(Path(artifacts_path))
            pipeline_options = PdfPipelineOptions(artifacts_path=artifacts_path)
            return DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
                }
            )
        return DocumentConverter()

    @staticmethod
    def _ensure_rapidocr_models(artifacts_path: Path) -> None:
        """Ensure RapidOCR artifacts exist under the configured Docling artifacts path."""
        required_paths = (
            artifacts_path
            / "RapidOcr"
            / "torch"
            / "PP-OCRv4"
            / "det"
            / "ch_PP-OCRv4_det_mobile.pth",
            artifacts_path
            / "RapidOcr"
            / "torch"
            / "PP-OCRv4"
            / "cls"
            / "ch_ptocr_mobile_v2.0_cls_mobile.pth",
            artifacts_path
            / "RapidOcr"
            / "torch"
            / "PP-OCRv4"
            / "rec"
            / "ch_PP-OCRv4_rec_mobile.pth",
            artifacts_path
            / "RapidOcr"
            / "paddle"
            / "PP-OCRv4"
            / "rec"
            / "ch_PP-OCRv4_rec_mobile"
            / "ppocr_keys_v1.txt",
            artifacts_path / "RapidOcr" / "resources" / "fonts" / "FZYTK.TTF",
        )
        if all(path.exists() for path in required_paths):
            return

        try:
            from docling.utils.model_downloader import download_models
        except ImportError:
            LOGGER.warning("Docling model downloader unavailable; skipping RapidOCR prefetch.")
            return

        artifacts_path.mkdir(parents=True, exist_ok=True)
        LOGGER.info(
            "RapidOCR models missing in %s. Downloading once to DOCLING_ARTIFACTS_PATH.",
            artifacts_path,
        )
        download_models(
            output_dir=artifacts_path,
            with_layout=False,
            with_tableformer=False,
            with_tableformer_v2=False,
            with_code_formula=False,
            with_picture_classifier=False,
            with_smolvlm=False,
            with_granitedocling=False,
            with_granitedocling_mlx=False,
            with_smoldocling=False,
            with_smoldocling_mlx=False,
            with_granite_vision=False,
            with_granite_chart_extraction=False,
            with_granite_chart_extraction_v4=False,
            with_rapidocr=True,
            with_easyocr=False,
        )
        if not all(path.exists() for path in required_paths):
            LOGGER.warning(
                "RapidOCR download finished but required model files are still missing under %s.",
                artifacts_path,
            )

    @staticmethod
    def _rows_from_table_text(text: str) -> list[list[str]]:
        """Parse textual table notation into a row/column matrix."""
        rows: list[list[str]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.fullmatch(r"[\-:|\s]+", stripped):
                continue
            if "|" in stripped:
                cols = [col.strip() for col in stripped.split("|") if col.strip()]
            elif "\t" in stripped:
                cols = [col.strip() for col in stripped.split("\t") if col.strip()]
            else:
                cols = [col.strip() for col in re.split(r"\s{2,}", stripped) if col.strip()]
            if cols:
                rows.append(cols)
        return rows

    @staticmethod
    def _coord_value(obj: Any, *keys: str) -> float | None:
        """Read one coordinate value from object attributes or mapping keys."""
        for key in keys:
            if hasattr(obj, key):
                value = getattr(obj, key)
                if isinstance(value, (int, float)):
                    return float(value)
            if isinstance(obj, dict) and key in obj and isinstance(obj[key], (int, float)):
                return float(obj[key])
        return None
