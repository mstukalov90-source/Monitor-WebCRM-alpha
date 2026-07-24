"""Fill OATI letter DOCX template and append map/photo pages."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph

MSK = ZoneInfo("Europe/Moscow")

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "oati_letter.docx"
MAP_WIDTH_CM_DOCX = 16.0

DEFAULT_VIOLATION = (
    "нормативный правовой акт города Москвы, требования которого были нарушены - "
    "часть 5 статьи 17 Закона города Москвы от 30.04.2014 № 18 "
    "«О благоустройстве в городе Москве»"
)

# Placeholders as they appear in the joined paragraph text (may be split across runs).
PH_DOC_DATE = "{cn{document.date(DateRU)(Concat:от | г. )}cn}"
PH_DOC_NUMBER = "{cn{document.number(Concat:№ |)}cn}"
PH_STREET = "{Улица на которой находится объект reports}"
PH_TODAY = "{Актуальное сегодняшнее число}"
PH_FID = "{fid из новой таблицы писем}"
PH_EXECUTOR = (
    "{Получаем из столбаца «Исполнитель», "
    "если работаем с задачей где этого нет можем ввести вручную или оставить пустым}"
)
PH_PHOTO_DT = (
    "{Дата и время берём из mggt_field.photos.created_at и нормализуем для РУ формата}"
)
PH_ADDRESS = (
    "{Получить адрес ближайшего здания к точке reports, "
    "использовать сторонние бесплатные сервисы, отображать только улицу и дом}"
)
PH_COORDS = "{координаты объекта reports}"
PH_ENG = (
    "{Получаем из столбаца data_mos.items62461_*.engineering_net_obj, "
    "если работаем с задачей где этого нет можем ввести вручную или оставить пустым}"
)
PH_DESCRIPTION = "{Ввод комментария вручную}"
PH_VIOLATION = (
    "{Ввод комментария вручную, по умолчанию заполнено : "
    "нормативный правовой акт города Москвы, требования которого были нарушены - "
    "часть 5 статьи 17 Закона города Москвы от 30.04.2014 № 18 "
    "«О благоустройстве в городе Москве»}"
)

# Soft line breaks lost during placeholder join — re-insert before these markers.
_LINE_BREAK_BEFORE = (
    "1. Сведения о производителе работ:",
    "7. Данные, указывающие на признаки наличия события административного правонарушения:",
)


def format_ru_date(dt: datetime | None = None) -> str:
    value = dt or datetime.now(MSK)
    if value.tzinfo is None:
        value = value.replace(tzinfo=MSK)
    else:
        value = value.astimezone(MSK)
    return value.strftime("%d.%m.%Y")


def format_ru_datetime(value: str | datetime | None) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return ""
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MSK)
    else:
        dt = dt.astimezone(MSK)
    return dt.strftime("%d.%m.%Y %H:%M")


def format_wgs84(lon: float, lat: float) -> str:
    return f"{lat:.6f}, {lon:.6f}"


def _ensure_structural_breaks(text: str) -> str:
    """Insert ``\\n`` before numbered section markers when missing."""
    result = text
    for marker in _LINE_BREAK_BEFORE:
        idx = 0
        while True:
            pos = result.find(marker, idx)
            if pos < 0:
                break
            if pos > 0 and result[pos - 1] != "\n":
                result = result[:pos] + "\n" + result[pos:]
                pos += 1
            idx = pos + len(marker)
    return result


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """Replace paragraph runs; ``\\n`` becomes a Word soft line break."""
    parts = text.split("\n")
    if not paragraph.runs:
        run = paragraph.add_run(parts[0])
        for part in parts[1:]:
            run.add_break(WD_BREAK.LINE)
            run = paragraph.add_run(part)
        return

    paragraph.runs[0].text = parts[0]
    for run in paragraph.runs[1:]:
        run.text = ""
    run = paragraph.runs[0]
    for part in parts[1:]:
        run.add_break(WD_BREAK.LINE)
        run = paragraph.add_run(part)


def _replace_in_paragraph(paragraph: Paragraph, mapping: dict[str, str]) -> None:
    # Soft line breaks appear as "\n" in paragraph.text and split placeholders.
    full = paragraph.text.replace("\r", "").replace("\n", "")
    if not full:
        return
    new_text = full
    changed = False
    for key, value in mapping.items():
        if key in new_text:
            new_text = new_text.replace(key, value)
            changed = True
    if changed:
        _set_paragraph_text(paragraph, _ensure_structural_breaks(new_text))


def _iter_all_paragraphs(document: Document):
    yield from document.paragraphs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def fill_letter_template(
    *,
    street: str,
    today: str,
    fid: int | str,
    executor: str,
    incident_datetime: str,
    address: str,
    coordinates: str,
    engineering: str,
    description: str,
    violation: str,
) -> Document:
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Letter template not found: {TEMPLATE_PATH}")

    document = Document(str(TEMPLATE_PATH))
    blank = "__________"
    # Longer placeholders first: PH_VIOLATION starts with PH_DESCRIPTION text.
    unique_map = {
        PH_DOC_DATE: f"от {today} г." if today else blank,
        PH_DOC_NUMBER: f"№ {fid}",
        PH_STREET: street or blank,
        PH_TODAY: today or blank,
        PH_FID: str(fid),
        PH_EXECUTOR: executor if executor else blank,
        PH_PHOTO_DT: incident_datetime if incident_datetime else blank,
        PH_ADDRESS: address if address else blank,
        PH_COORDS: coordinates if coordinates else blank,
        PH_ENG: engineering if engineering else blank,
        PH_VIOLATION: violation if violation else DEFAULT_VIOLATION,
        PH_DESCRIPTION: description if description else blank,
    }
    for paragraph in _iter_all_paragraphs(document):
        _replace_in_paragraph(paragraph, unique_map)
    return document


def _add_page_break(document: Document) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    run.add_break(WD_BREAK.PAGE)


def append_map_page(document: Document, map_png: bytes, title: str = "Ситуационный план") -> None:
    _add_page_break(document)
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(title)
    run.bold = True
    run.font.size = Pt(14)

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(io.BytesIO(map_png), width=Cm(MAP_WIDTH_CM_DOCX))

    caption = document.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = caption.add_run("Масштаб 1:1000. Красный маркер — объект reports; синий — объект задачи.")
    cap.font.size = Pt(9)


def append_photo_pages(
    document: Document,
    photos: list[tuple[bytes, str]],
) -> None:
    """Append photos starting on a new page; several photos may share a page."""
    if not photos:
        _add_page_break(document)
        p = document.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run("Фотофиксация: фотографии не выбраны.")
        return

    _add_page_break(document)
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run("Фотофиксация")
    run.bold = True
    run.font.size = Pt(14)

    for index, (image_bytes, label) in enumerate(photos):
        if index > 0 and index % 2 == 0:
            _add_page_break(document)
            h = document.add_paragraph()
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = h.add_run("Фотофиксация (продолжение)")
            r.bold = True
            r.font.size = Pt(14)

        caption = document.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.LEFT
        caption.add_run(label)

        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        try:
            run.add_picture(io.BytesIO(image_bytes), width=Cm(14.0))
        except Exception:
            paragraph.add_run(" [не удалось вставить изображение] ")


def document_to_bytes(document: Document) -> bytes:
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
