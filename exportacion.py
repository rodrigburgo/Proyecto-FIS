"""RF-09 / CU-12, CU-13: Exportador a Excel y PDF."""
import io
from datetime import datetime

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def a_excel(hojas: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for nombre, df in hojas.items():
            df = df.copy()
            for c in df.select_dtypes(include=["datetimetz"]).columns:
                df[c] = df[c].dt.tz_localize(None)
            df.to_excel(xw, sheet_name=nombre[:31], index=False)
            ws = xw.sheets[nombre[:31]]
            for celda in ws[1]:
                celda.font = Font(bold=True, color="FFFFFF")
                celda.fill = PatternFill("solid", fgColor="C0392B")
                celda.alignment = Alignment(horizontal="center")
            for i, col in enumerate(df.columns, 1):
                ancho = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)]) + 2
                ws.column_dimensions[get_column_letter(i)].width = min(ancho, 45)
            ws.freeze_panes = "A2"
    return buf.getvalue()


def a_pdf(titulo: str, filtros: str, kpis: dict[str, str], tablas: dict[str, pd.DataFrame], max_filas: int = 15) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    est = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    el = [Paragraph(titulo, est["Title"]),
          Paragraph(f"Generado: {datetime.now():%Y-%m-%d %H:%M}", est["Normal"]),
          Paragraph(f"Filtros: {filtros}", est["Normal"]), Spacer(1, 10)]
    fila_k = [[Paragraph(f"<b>{v}</b><br/><font size=8>{k}</font>", est["Normal"]) for k, v in kpis.items()]]
    tk = Table(fila_k)
    tk.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, colors.grey), ("INNERGRID", (0, 0), (-1, -1), .25, colors.lightgrey),
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F6F8")), ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    el += [tk, Spacer(1, 14)]
    for nombre, df in tablas.items():
        if df is None or df.empty:
            continue
        el.append(Paragraph(nombre, est["Heading3"]))
        d = df.head(max_filas).copy()
        d = d.map(lambda x: f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x))
        t = Table([list(d.columns)] + d.values.tolist(), repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C0392B")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("GRID", (0, 0), (-1, -1), .25, colors.lightgrey),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")])]))
        el += [t, Spacer(1, 12)]
    doc.build(el)
    return buf.getvalue()
