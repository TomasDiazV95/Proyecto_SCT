from io import BytesIO

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def excel_response(headers: list[str], rows: list[dict], sheet_title: str, filename: str) -> StreamingResponse:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    for row in rows:
        ws.append([row.get(header) for header in headers])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def workbook_response(sheets: list[dict], filename: str) -> StreamingResponse:
    """Libro con varias hojas. Cada hoja: title, headers, rows y, opcionales, widths (ancho por columna)
    y number_formats ({header: formato}, se aplica solo a celdas con numero o fecha)."""
    wb = Workbook()
    wb.remove(wb.active)
    for sheet in sheets:
        ws = wb.create_sheet(sheet["title"])
        headers = sheet["headers"]
        formats = sheet.get("number_formats") or {}
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in sheet["rows"]:
            ws.append([row.get(header) for header in headers])
            for idx, header in enumerate(headers, start=1):
                cell = ws.cell(row=ws.max_row, column=idx)
                if header in formats and not isinstance(cell.value, str) and cell.value is not None:
                    cell.number_format = formats[header]
        for idx, width in enumerate(sheet.get("widths") or [], start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
