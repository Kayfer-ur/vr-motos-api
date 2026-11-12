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
CAPITAL = 120000.0     # capital aplicado (base do comparativo)
LUCRO_POR_MOTO = 700.0
ORCAMENTO_COMPRA = 90000.0

COR_OURO = colors.HexColor("#ca8a04")
COR_FUNDO = colors.HexColor("#161616")
COR_FUNDO_ALT = colors.HexColor("#1e1e1e")
COR_LINHA = colors.HexColor("#2a2a2a")

PAG_W, PAG_H = A4
MARGEM = 1.6 * cm


def _ciclo(data_venda):
    """Mesma regra do 'Mês VR': dia >= 21 pertence ao ciclo (mês) seguinte."""
    if data_venda is None:
        return None
    if data_venda.day >= 21:
        return str(data_venda.month % 12 + 1)
    return str(data_venda.month)


def _brl(v):
    """Máscara universal de moeda brasileira: R$ 18.000,00."""
    v = float(v or 0)
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v):
    """Formata percentual no padrão brasileiro: 1,17%."""
    v = float(v or 0)
    return f"{v:.2f}".replace(".", ",") + "%"


def _upper(v):
    """Padroniza textos de montadoras/modelos/cor/chassi em maiúsculas."""
    return (v or "").strip().upper() or "—"


def _rendimento_selic():
    return CAPITAL * (SELIC_MENSAL / 100)


def _cabecalho_rodape(canvas, doc):
    canvas.saveState()
    # Cabeçalho
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(COR_OURO)
    canvas.drawString(MARGEM, PAG_H - MARGEM + 0.55 * cm, "VR Multimarcas")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(PAG_W - MARGEM, PAG_H - MARGEM + 0.55 * cm, "Relatório Executivo")
    canvas.setStrokeColor(COR_OURO)
    canvas.setLineWidth(1.2)
    canvas.line(MARGEM, PAG_H - MARGEM, PAG_W - MARGEM, PAG_H - MARGEM)
    # Rodapé
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(MARGEM, MARGEM - 0.7 * cm, "Documento gerado automaticamente")
    canvas.drawRightString(PAG_W - MARGEM, MARGEM - 0.7 * cm, f"Página {doc.page}")
    canvas.restoreState()


def _tabela_chave_valor(pares):
    t = Table(pares, colWidths=[7 * cm, 8 * cm])
    estilo = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, COR_LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    for i in range(len(pares)):
        estilo.append(("BACKGROUND", (0, i), (-1, i), COR_FUNDO if i % 2 == 0 else COR_FUNDO_ALT))
    t.setStyle(TableStyle(estilo))
    return t


def _tabela_motos(data, larguras):
    t = Table(data, colWidths=larguras, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_OURO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, COR_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    for i in range(1, len(data)):
        estilo.append(("BACKGROUND", (0, i), (-1, i), COR_FUNDO if i % 2 == 1 else COR_FUNDO_ALT))
    t.setStyle(TableStyle(estilo))
    return t


def _montar_pdf(mes: str, db: Session) -> bytes:
    vendidas = [m for m in db.query(Moto).filter(Moto.status == "Vendido").all() if _ciclo(m.data_venda) == mes]
    estoque = db.query(Moto).filter(Moto.status == "Estoque").all()

    faturamento = sum(float(m.preco or 0) for m in vendidas)
    lucro_vendas = len(vendidas) * LUCRO_POR_MOTO
    rend_selic = _rendimento_selic()
    diferenca = lucro_vendas - rend_selic
    capital_alocado = sum(float(m.preco or 0) for m in estoque)
    disponivel_compras = ORCAMENTO_COMPRA - capital_alocado
    roi = (lucro_vendas / CAPITAL) * 100 if CAPITAL else 0.0

    # Comparativo de custo de oportunidade (vocabulário executivo)
    if diferenca > 0:
        comparativo_texto = f"Superávit de Performance vs. Taxa Selic: + {_brl(diferenca)} (Alpha Positivo)"
    elif diferenca < 0:
        comparativo_texto = f"Déficit de Performance vs. Taxa Selic: - {_brl(abs(diferenca))} (Alpha Negativo)"
    else:
        comparativo_texto = "Performance Neutra vs. Taxa Selic (Alpha Zero)"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=MARGEM + 1.2 * cm,
        bottomMargin=MARGEM + 0.8 * cm,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        title=f"Relatório de Rentabilidade — Mês VR {mes}",
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle("Titulo", parent=styles["Title"], fontSize=20, textColor=colors.white, spaceAfter=2, leading=24)
    sub = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=16)
    secao = ParagraphStyle("Secao", parent=styles["Heading2"], fontSize=13, textColor=COR_OURO, spaceBefore=14, spaceAfter=8)
    corpo = ParagraphStyle("Corpo", parent=styles["Normal"], fontSize=10, leading=15, textColor=colors.white)
    # Chassi em fonte monoespaçada, forçando a separação visual da coluna "Cor"
    chassi_style = ParagraphStyle("Chassi", parent=styles["Normal"], fontName="Courier", fontSize=7, textColor=colors.white, leading=9)

    story = [
        Paragraph(f"Relatório de Rentabilidade — Mês VR {mes}", titulo),
        Paragraph(f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}", sub),
    ]

    # Resumo Executivo
    story.append(Paragraph("Resumo Executivo", secao))
    story.append(_tabela_chave_valor([
        ["Volume de Vendas (Unidades)", str(len(vendidas))],
        ["Estoque Atual (Unidades)", str(len(estoque))],
        ["Receita Bruta (Vendas)", _brl(faturamento)],
        ["Lucro Operacional", _brl(lucro_vendas)],
        ["ROI (Retorno sobre o Investimento)", _pct(roi)],
    ]))
    story.append(Spacer(1, 0.4 * cm))

    # Comparativo de Custo de Oportunidade
    story.append(Paragraph("Comparativo de Custo de Oportunidade", secao))
    story.append(_tabela_chave_valor([
        ["Capital Aplicado", _brl(CAPITAL)],
        [f"Rendimento Selic ({_pct(SELIC_MENSAL)} a.m.)", _brl(rend_selic)],
        ["Rendimento Operacional (Motos)", _brl(lucro_vendas)],
        ["Resultado", comparativo_texto],
    ]))
    story.append(Spacer(1, 0.4 * cm))

    # Capital Alocado (Em Estoque)
    story.append(Paragraph("Capital Alocado (Em Estoque)", secao))
    story.append(_tabela_chave_valor([
        ["Orçamento Total", _brl(ORCAMENTO_COMPRA)],
        ["Capital Alocado", _brl(capital_alocado)],
        ["Disponível para Compras", _brl(disponivel_compras)],
    ]))
    story.append(Spacer(1, 0.4 * cm))

    # Vendas realizadas no mês
    story.append(Paragraph(f"Vendas Realizadas no Mês ({len(vendidas)})", secao))
    if vendidas:
        data_v = [["Marca", "Modelo", "Ano", "Chassi", "Cor", "Preço", "Lucro"]]
        for m in vendidas:
            data_v.append([
                _upper(m.marca),
                _upper(m.modelo),
                str(m.ano),
                Paragraph(_upper(m.chassi), chassi_style),
                _upper(m.cor),
                _brl(m.preco),
                _brl(LUCRO_POR_MOTO),
            ])
        story.append(_tabela_motos(data_v, [2.2 * cm, 2.8 * cm, 1.0 * cm, 3.4 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm]))
    else:
        story.append(Paragraph("Nenhuma venda realizada neste ciclo.", corpo))
    story.append(Spacer(1, 0.4 * cm))

    # Estoque atual
    story.append(Paragraph(f"Estoque Atual ({len(estoque)})", secao))
    if estoque:
        data_e = [["Marca", "Modelo", "Ano", "Chassi", "Cor", "Preço"]]
        for m in estoque:
            data_e.append([
                _upper(m.marca),
                _upper(m.modelo),
                str(m.ano),
                Paragraph(_upper(m.chassi), chassi_style),
                _upper(m.cor),
                _brl(m.preco),
            ])
        story.append(_tabela_motos(data_e, [2.4 * cm, 3.0 * cm, 1.2 * cm, 3.4 * cm, 1.8 * cm, 3.0 * cm]))
    else:
        story.append(Paragraph("Nenhuma moto em estoque.", corpo))

    doc.build(story, onFirstPage=_cabecalho_rodape, onLaterPages=_cabecalho_rodape)
    buf.seek(0)
    return buf.getvalue()


@router.get("/detalhado")
def relatorio_detalhado(mes: str = Query(...), db: Session = Depends(get_db), _u: dict = Depends(get_usuario_atual)):
    """Relatório executivo em PDF (único tipo de relatório)."""
    pdf = _montar_pdf(mes, db)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="relatorio_mes_{mes}.pdf"'},
    )
