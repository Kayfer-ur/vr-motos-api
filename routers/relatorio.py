import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from auth import get_usuario_atual
from database import get_db
from models import Moto

router = APIRouter(prefix="/relatorio", tags=["Relatórios"])

SELIC_MENSAL = 1.07    # % ao mês
CAPITAL = 120000.0     # capital comparativo fixo
LUCRO_POR_MOTO = 700.0
ORCAMENTO_COMPRA = 90000.0  # limite para compra de motos

COR_OURO = colors.HexColor("#ca8a04")
COR_FUNDO = colors.HexColor("#161616")
COR_LINHA = colors.HexColor("#2a2a2a")


def _ciclo(data_venda):
    """Mesma regra do 'Mês VR': dia >= 21 pertence ao ciclo (mês) seguinte."""
    if data_venda is None:
        return None
    if data_venda.day >= 21:
        return str(data_venda.month % 12 + 1)
    return str(data_venda.month)


def _brl(v):
    """Formata um número como moeda brasileira (R$ 1.234,56)."""
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _rendimento_selic():
    return CAPITAL * (SELIC_MENSAL / 100)


def _montar_pdf(mes: str, detalhado: bool, db: Session) -> bytes:
    vendidas = [m for m in db.query(Moto).filter(Moto.status == "Vendido").all() if _ciclo(m.data_venda) == mes]
    estoque = db.query(Moto).filter(Moto.status == "Estoque").all()

    faturamento = sum(float(m.preco or 0) for m in vendidas)
    lucro_vendas = len(vendidas) * LUCRO_POR_MOTO
    rend_selic = _rendimento_selic()
    diferenca = lucro_vendas - rend_selic
    capital_parado = sum(float(m.preco or 0) for m in estoque)
    disponivel_compras = ORCAMENTO_COMPRA - capital_parado

    if diferenca > 0:
        comparativo_texto = f"O rendimento da loja foi {_brl(diferenca)} acima da Selic"
    elif diferenca < 0:
        comparativo_texto = f"O rendimento da loja foi {_brl(abs(diferenca))} abaixo da Selic"
    else:
        comparativo_texto = "O rendimento da loja foi igual ao da Selic"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        title=f"Relatório VR Multimarcas — Mês {mes}",
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle("AppTitulo", parent=styles["Title"], fontSize=24, textColor=COR_OURO, spaceAfter=2)
    sub = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=14)
    secao = ParagraphStyle("Secao", parent=styles["Heading2"], fontSize=14, textColor=colors.white, spaceBefore=12, spaceAfter=6)
    corpo = ParagraphStyle("Corpo", parent=styles["Normal"], fontSize=10, leading=15, textColor=colors.white)

    story = [Paragraph("VR Multimarcas", titulo)]
    story.append(Paragraph(
        f"Relatório {'Detalhado' if detalhado else 'Resumido'} — Mês VR {mes} — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        sub,
    ))

    # ---- Comparativo financeiro (sempre presente) ----
    story.append(Paragraph("Comparativo Financeiro", secao))
    comparativo = [
        ["Capital aplicado", _brl(CAPITAL)],
        [f"Rendimento Selic ({SELIC_MENSAL}% a.m.)", _brl(rend_selic)],
        ["Lucro das vendas (motos)", _brl(lucro_vendas)],
        ["Comparativo", comparativo_texto],
    ]
    tc = Table(comparativo, colWidths=[7 * cm, 8 * cm])
    tc.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.white),
        ("BACKGROUND", (0, 0), (-1, -1), COR_FUNDO),
        ("GRID", (0, 0), (-1, -1), 0.3, COR_LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tc)
    story.append(Spacer(1, 0.5 * cm))

    # ---- Gestão de compras (sempre presente) ----
    story.append(Paragraph("Gestão de Compras", secao))
    compras = [
        ["Orçamento Total", _brl(ORCAMENTO_COMPRA)],
        ["Capital Alocado (Em Estoque)", _brl(capital_parado)],
        ["Disponível para Compras", _brl(disponivel_compras)],
    ]
    tg = Table(compras, colWidths=[7 * cm, 8 * cm])
    tg.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.white),
        ("BACKGROUND", (0, 0), (-1, -1), COR_FUNDO),
        ("GRID", (0, 0), (-1, -1), 0.3, COR_LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tg)
    story.append(Spacer(1, 0.5 * cm))

    if detalhado:
        # ---- Motos vendidas no mês ----
        story.append(Paragraph(f"Motos Vendidas no Mês ({len(vendidas)})", secao))
        if vendidas:
            data_v = [["Marca", "Modelo", "Ano", "Chassi", "Preço", "Lucro"]]
            for m in vendidas:
                data_v.append([
                    m.marca, m.modelo, str(m.ano), m.chassi or "—",
                    _brl(float(m.preco or 0)), _brl(LUCRO_POR_MOTO),
                ])
            tv = Table(data_v, colWidths=[2.2 * cm, 3.4 * cm, 1.2 * cm, 3.4 * cm, 2.6 * cm, 2.6 * cm], repeatRows=1)
            tv.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COR_OURO),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), COR_FUNDO),
                ("GRID", (0, 0), (-1, -1), 0.3, COR_LINHA),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(tv)
        else:
            story.append(Paragraph("Nenhuma moto vendida neste ciclo.", corpo))
        story.append(Spacer(1, 0.5 * cm))

        # ---- Motos em estoque ----
        story.append(Paragraph(f"Motos em Estoque ({len(estoque)})", secao))
        if estoque:
            data_e = [["Marca", "Modelo", "Ano", "Chassi", "Preço"]]
            for m in estoque:
                data_e.append([
                    m.marca, m.modelo, str(m.ano), m.chassi or "—", _brl(float(m.preco or 0)),
                ])
            te = Table(data_e, colWidths=[2.6 * cm, 4 * cm, 1.4 * cm, 4 * cm, 3 * cm], repeatRows=1)
            te.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COR_OURO),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), COR_FUNDO),
                ("GRID", (0, 0), (-1, -1), 0.3, COR_LINHA),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(te)
        else:
            story.append(Paragraph("Nenhuma moto em estoque.", corpo))
    else:
        # ---- Resumido: só totais ----
        story.append(Paragraph("Totais", secao))
        resumo = [
            ["Motos vendidas no mês", str(len(vendidas))],
            ["Motos em estoque", str(len(estoque))],
            ["Faturamento total (vendas)", _brl(faturamento)],
            ["Comparativo", comparativo_texto],
        ]
        tr = Table(resumo, colWidths=[7 * cm, 8 * cm])
        tr.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
            ("TEXTCOLOR", (1, 0), (1, -1), colors.white),
            ("BACKGROUND", (0, 0), (-1, -1), COR_FUNDO),
            ("GRID", (0, 0), (-1, -1), 0.3, COR_LINHA),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tr)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


@router.get("/detalhado")
def relatorio_detalhado(mes: str = Query(...), db: Session = Depends(get_db), _u: dict = Depends(get_usuario_atual)):
    """Relatório detalhado em PDF: vendidas, estoque e comparativo financeiro."""
    pdf = _montar_pdf(mes, detalhado=True, db=db)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="relatorio_detalhado_mes_{mes}.pdf"'},
    )


@router.get("/resumido")
def relatorio_resumido(mes: str = Query(...), db: Session = Depends(get_db), _u: dict = Depends(get_usuario_atual)):
    """Relatório resumido em PDF: apenas totais e veredito."""
    pdf = _montar_pdf(mes, detalhado=False, db=db)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="relatorio_resumido_mes_{mes}.pdf"'},
    )
