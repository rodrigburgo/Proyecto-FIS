"""Figuras Plotly con estilo tipo BI (listas para presentar; cada una se puede descargar como PNG desde su barra)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .validador import ETIQUETAS_EDAD

ROJO, GRIS, AZUL = "#C0392B", "#7F8C8D", "#2C7BB6"
ESCALA = ["#FDEDEC", "#F5B7B1", "#E74C3C", "#922B21"]
ORDEN_TRIAGE = ["I", "II", "III", "IV", "V"]


def _estilo(fig, titulo, alto=360):
    fig.update_layout(title=dict(text=titulo, x=0, font=dict(size=16)), template="plotly_white", height=alto,
                      margin=dict(l=10, r=10, t=50, b=10), font=dict(family="Inter, Arial", size=12),
                      legend=dict(orientation="h", y=-0.2), colorway=[ROJO, AZUL, GRIS, "#F39C12", "#27AE60"])
    return fig


def serie_mensual(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["mes"], y=df["total"], name="Atenciones", mode="lines+markers", fill="tozeroy",
                             line=dict(color=ROJO), fillcolor="rgba(192,57,43,.12)"))
    fig.add_trace(go.Scatter(x=df["mes"], y=df["reincidentes"], name="Reincidentes", mode="lines+markers",
                             line=dict(color=AZUL, dash="dot")))
    return _estilo(fig, "Atenciones por mes")


def barras_h(df, cat, valor, titulo, texto=".0f", color=ROJO, top=None):
    d = df.sort_values(valor, ascending=False).head(top) if top else df.sort_values(valor, ascending=False)
    fig = px.bar(d.iloc[::-1], x=valor, y=cat, orientation="h", text=valor, color_discrete_sequence=[color])
    fig.update_traces(texttemplate="%{text:" + (",.0f" if texto == ".0f" else ".1f") + "}", textposition="outside", cliponaxis=False)
    fig.update_layout(xaxis_title=None, yaxis_title=None)
    return _estilo(fig, titulo, max(320, 28 * len(d) + 110))


def rango_edad(df):
    df = df.set_index("rango_edad").reindex([e for e in ETIQUETAS_EDAD if e in set(df["rango_edad"])]).reset_index()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=df["rango_edad"], y=df["total"], name="Atenciones", marker_color=ROJO, secondary_y=False)
    fig.add_scatter(x=df["rango_edad"], y=df["pct_reincidencia"], name="% reincidencia", mode="lines+markers",
                    line=dict(color=AZUL), secondary_y=True)
    fig.update_yaxes(title_text="Atenciones", secondary_y=False)
    fig.update_yaxes(title_text="% reincidencia", secondary_y=True, rangemode="tozero")
    return _estilo(fig, "Atenciones y reincidencia por rango de edad")


def heatmap(df, valor, titulo):
    p = df.pivot_table(index="especialidad", columns="rango_edad", values=valor)
    p = p.reindex(columns=[e for e in ETIQUETAS_EDAD if e in p.columns])
    fig = px.imshow(p, text_auto=".1f", aspect="auto", color_continuous_scale=ESCALA)
    fig.update_layout(xaxis_title="Rango de edad", yaxis_title=None, coloraxis_colorbar_title="%")
    return _estilo(fig, titulo, max(340, 38 * len(p) + 120))


def dona(df, cat, titulo, orden=None):
    d = df.copy()
    if orden:
        d[cat] = pd.Categorical(d[cat], categories=orden, ordered=True)
        d = d.sort_values(cat)
    fig = px.pie(d, names=cat, values="total", hole=.55, color_discrete_sequence=px.colors.sequential.Reds_r)
    fig.update_traces(textinfo="percent+label", sort=False)
    return _estilo(fig, titulo)


def columnas(df, cat, valor, titulo, formato=None):
    fig = px.bar(df, x=cat, y=valor, text=valor, color_discrete_sequence=[ROJO])
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(xaxis_title=None, yaxis_title=None)
    return _estilo(fig, titulo)


def linea(df, x, y, titulo):
    fig = px.line(df, x=x, y=y, markers=True, color_discrete_sequence=[ROJO])
    fig.update_layout(xaxis_title=None, yaxis_title="%")
    return _estilo(fig, titulo)
