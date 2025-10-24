# pages/specific_dash.py (CORRIGIDO)

import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime
from io import StringIO
import base64
import plotly.express as px

# Importa o app central e helpers
from app import app, TEMPLATE_GRAFICO_MODERNO
from data_source import PONTOS_DE_ANALISE, FREQUENCIA_SIMULACAO  # Importa a frequência
import processamento  # Importa definir_status_chuva e definir_status_umidade_hierarquico
import gerador_pdf

# --- Mapa de Cores para Umidade ---
CORES_UMIDADE = {'umidade_1m_perc': 'green', 'umidade_2m_perc': 'gold', 'umidade_3m_perc': 'red'}
# Mapeamento de Risco (Usado localmente)
RISCO = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3, "SEM DADOS": -1, "INDEFINIDO": -1}
mapa_status_cor_geral = {0: ("LIVRE", "success"), 1: ("ATENÇÃO", "warning"), 2: ("ALERTA", "orange"),
                         3: ("PARALIZAÇÃO", "danger"), -1: ("SEM DADOS", "secondary")}


# --- Layout da Página Específica ---
def get_layout():
    # ... (Layout idêntico à versão anterior) ...
    opcoes_tempo = [{'label': f'Últimas {h} horas', 'value': h} for h in [1, 3, 6, 12, 18, 24, 72, 84, 96]] + [
        {'label': 'Todo o Histórico', 'value': 14 * 24}]
    return dbc.Container([
        dcc.Store(id='store-id-ponto-ativo'),
        dbc.Row([dbc.Col(html.H2(id='specific-dash-title', children="Carregando..."), width=12, lg=9),
                 dbc.Col(dbc.Button("Voltar ao Mapa", color="secondary", href="/", size="lg", className="w-100"),
                         width=12, lg=3, className="my-2 my-lg-0")], className="my-4 align-items-center"),
        dbc.Row(id='specific-dash-cards', children=[dbc.Spinner(size="lg")]),
        dbc.Row([dbc.Col(dbc.Label("Período (Gráficos):"), width="auto"), dbc.Col(
            dcc.Dropdown(id='graph-time-selector', options=opcoes_tempo, value=72, clearable=False, searchable=False),
            width=12, lg=4)], align="center", className="my-3"),
        dbc.Row(id='specific-dash-graphs', children=[dbc.Spinner(size="lg")], className="my-4"),
        dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([html.H4("Gerar Relatório em PDF", className="card-title"),
                                                html.P("Este relatório será gerado para o ponto atual."),
                                                dcc.DatePickerRange(id='pdf-date-picker', start_date=(
                                                        pd.Timestamp.now() - pd.Timedelta(days=7)).date(),
                                                                    end_date=pd.Timestamp.now().date(),
                                                                    display_format='DD/MM/YYYY', className="mb-3"),
                                                html.Br(), dcc.Loading(id="loading-pdf", type="default", children=[
                html.Div([dbc.Button("Gerar e Baixar PDF", id='btn-pdf-especifico', color="primary", size="lg"),
                          dcc.Download(id='download-pdf-especifico')])])]), className="shadow-sm text-center"),
                         className="mb-5")]),
    ], fluid=True)


# --- Callbacks da Página Específica ---

# Callback 1: Atualiza o dashboard - CORRIGIDO
@app.callback(
    Output('specific-dash-title', 'children'),
    Output('specific-dash-cards', 'children'),
    Output('specific-dash-graphs', 'children'),
    Output('store-id-ponto-ativo', 'data'),
    Input('url', 'pathname'),
    Input('store-dados-sessao', 'data'),
    Input('graph-time-selector', 'value')
)
def update_specific_dashboard(pathname, dados_json, selected_hours):
    if not dados_json or not pathname.startswith('/ponto/') or selected_hours is None:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    id_ponto = ""
    try:
        id_ponto = pathname.split('/')[-1];
        config = PONTOS_DE_ANALISE[id_ponto]
    except KeyError:
        return "Ponto não encontrado", "Erro: Ponto inválido.", "", None

    df_completo = pd.read_json(StringIO(dados_json), orient='split');
    df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
    df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
    if df_ponto.empty: return f"Dashboard: {config['nome']}", "Sem dados.", "", id_ponto

    # Calcula dados e status individuais
    df_chuva_72h = processamento.calcular_acumulado_72h(df_ponto)
    if df_chuva_72h.empty: return f"Dashboard: {config['nome']}", "Calculando...", "", id_ponto
    ultimo_dado = df_ponto.iloc[-1]
    ultima_chuva_72h = df_chuva_72h.iloc[-1]['chuva_mm'] if not df_chuva_72h.empty else None
    umidade_1m_atual = ultimo_dado.get('umidade_1m_perc', None)
    umidade_2m_atual = ultimo_dado.get('umidade_2m_perc', None)
    umidade_3m_atual = ultimo_dado.get('umidade_3m_perc', None)
    base_1m = config['constantes'].get('UMIDADE_BASE_1M', 0.0)
    base_2m = config['constantes'].get('UMIDADE_BASE_2M', 0.0)
    base_3m = config['constantes'].get('UMIDADE_BASE_3M', 0.0)

    status_chuva_txt, status_chuva_col = processamento.definir_status_chuva(ultima_chuva_72h)
    status_umid_txt, status_umid_col, _ = processamento.definir_status_umidade_hierarquico(
        umidade_1m_atual, umidade_2m_atual, umidade_3m_atual, base_1m, base_2m, base_3m
    )

    # Determina o status GERAL mais crítico para o card
    risco_chuva = RISCO.get(status_chuva_txt, -1)
    risco_umidade = RISCO.get(status_umid_txt, -1)
    risco_geral = max(risco_chuva, risco_umidade)
    status_geral_texto, status_geral_cor = mapa_status_cor_geral.get(risco_geral, ("INDEFINIDO", "secondary"))

    if pd.isna(ultima_chuva_72h): ultima_chuva_72h = 0.0
    if pd.isna(umidade_3m_atual): umidade_3m_atual = 0.0

    # Layout dos Cards
    layout_cards = [
        dbc.Col(dbc.Card(dbc.CardBody([html.H5("Status Atual"), html.P(status_geral_texto, className="fs-3 fw-bold")]),
                         color=status_geral_cor, inverse=(status_geral_cor != "secondary"), className="shadow"), xs=12,
                md=4, className="mb-4"),
        dbc.Col(dbc.Card(
            dbc.CardBody([html.H5("Chuva 72h"), html.P(f"{ultima_chuva_72h:.1f} mm", className="fs-3 fw-bold")]),
            className="shadow"), xs=12, md=4, className="mb-4"),
        dbc.Col(dbc.Card(
            dbc.CardBody([html.H5("Umidade (3m)"), html.P(f"{umidade_3m_atual:.1f} %", className="fs-3 fw-bold")]),
            className="shadow"), xs=12, md=4, className="mb-4"),
    ]

    # --- INÍCIO DA CORREÇÃO DO FILTRO DE GRÁFICO ---
    # O seletor 'selected_hours' está em HORAS.
    # O simulador gera 1 ponto a cada 10 minutos (6 pontos por hora).
    # Precisamos converter as horas selecionadas em número de pontos.

    # Calcula pontos por hora (60 min / 10 min = 6)
    PONTOS_POR_HORA = int(60 / (FREQUENCIA_SIMULACAO.total_seconds() / 60))
    n_pontos_desejados = selected_hours * PONTOS_POR_HORA

    # n_pontos_plot é o número de PONTOS a exibir
    n_pontos_plot = min(n_pontos_desejados, len(df_ponto))

    # Filtra dados para gráficos usando o número correto de pontos
    df_ponto_plot = df_ponto.tail(n_pontos_plot);
    df_chuva_72h_plot = df_chuva_72h.tail(n_pontos_plot)

    # A variável 'n_horas_titulo' é usada apenas para o título do gráfico
    n_horas_titulo = selected_hours
    # --- FIM DA CORREÇÃO ---

    # Gráfico de Chuva
    fig_chuva = make_subplots(specs=[[{"secondary_y": True}]])
    fig_chuva.add_trace(
        go.Bar(x=df_ponto_plot['timestamp'], y=df_ponto_plot['chuva_mm'], name='Pluviometria Horária (mm)',
               marker_color='#2C3E50', opacity=0.8), secondary_y=False)
    fig_chuva.add_trace(go.Scatter(x=df_chuva_72h_plot['timestamp'], y=df_chuva_72h_plot['chuva_mm'],
                                   name='Precipitação Acumulada (mm)', mode='lines',
                                   line=dict(color='#007BFF', width=2.5)), secondary_y=True)
    # Usa n_horas_titulo no título
    fig_chuva.update_layout(title_text=f"Pluviometria ({n_horas_titulo}h)", template=TEMPLATE_GRAFICO_MODERNO,
                            margin=dict(l=40, r=20, t=50, b=40),
                            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor='center', x=0.5),
                            xaxis_title="Data e Hora", yaxis_title="Pluviometria Horária (mm)",
                            yaxis2_title="Precipitação Acumulada (mm)", hovermode="x unified", bargap=0.1)
    fig_chuva.update_yaxes(title_text="Pluviometria Horária (mm)", secondary_y=False);
    fig_chuva.update_yaxes(title_text="Precipitação Acumulada (mm)", secondary_y=True)

    # Gráfico de Umidade
    df_umidade = df_ponto_plot.melt(id_vars=['timestamp'],
                                    value_vars=['umidade_1m_perc', 'umidade_2m_perc', 'umidade_3m_perc'],
                                    var_name='Sensor', value_name='Umidade (%)')
    # Usa n_horas_titulo no título
    fig_umidade = px.line(df_umidade, x='timestamp', y='Umidade (%)', color='Sensor',
                          title=f"Variação da Umidade ({n_horas_titulo}h)", color_discrete_map=CORES_UMIDADE)
    fig_umidade.update_traces(line=dict(width=3));
    fig_umidade.update_layout(template=TEMPLATE_GRAFICO_MODERNO, margin=dict(l=40, r=20, t=40, b=50),
                              legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
    layout_graficos = [
        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_chuva)), className="shadow-sm"), width=12, className="mb-4"),
        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_umidade)), className="shadow-sm"), width=12,
                className="mb-4"), ]
    return f"Dashboard Detalhado: {config['nome']}", layout_cards, layout_graficos, id_ponto


# Callback 2: Gerar o PDF - CORRIGIDO
@app.callback(
    Output('download-pdf-especifico', 'data'),
    Input('btn-pdf-especifico', 'n_clicks'),
    [State('pdf-date-picker', 'start_date'), State('pdf-date-picker', 'end_date'),
     State('store-id-ponto-ativo', 'data'), State('store-dados-sessao', 'data')]
)
def gerar_download_pdf_especifico(n_clicks, start_date_str, end_date_str, id_ponto, dados_json):
    if not n_clicks or not id_ponto or not dados_json: return dash.no_update

    # Adiciona try/except para config
    try:
        config = PONTOS_DE_ANALISE[id_ponto]
    except KeyError:
        print("Erro PDF: id_ponto não encontrado");
        return dash.no_update

    df_completo = pd.read_json(StringIO(dados_json), orient='split');
    df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
    df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
    try:
        start_date_dt = pd.to_datetime(start_date_str).tz_localize('UTC');
        end_date_dt = (
                pd.to_datetime(end_date_str) + pd.Timedelta(days=1)).tz_localize('UTC')
    except Exception as e:
        print(f"Erro datas PDF: {e}");
        return dash.no_update
    df_periodo = df_ponto[(df_ponto['timestamp'] >= start_date_dt) & (df_ponto['timestamp'] < end_date_dt)].copy()
    if df_periodo.empty: print("Sem dados período PDF."); return dash.no_update

    # Calcula status GERAL para o PDF
    df_chuva_72h_pdf = processamento.calcular_acumulado_72h(df_periodo)
    if df_chuva_72h_pdf.empty: print("Sem chuva período PDF."); return dash.no_update

    ultimo_dado_pdf = df_periodo.iloc[-1]
    ultima_chuva_pdf = df_chuva_72h_pdf.iloc[-1]['chuva_mm'] if not df_chuva_72h_pdf.empty else None
    umidade_1m_pdf = ultimo_dado_pdf.get('umidade_1m_perc', None)
    umidade_2m_pdf = ultimo_dado_pdf.get('umidade_2m_perc', None)
    umidade_3m_pdf = ultimo_dado_pdf.get('umidade_3m_perc', None)
    base_1m = config['constantes'].get('UMIDADE_BASE_1M', 0.0)
    base_2m = config['constantes'].get('UMIDADE_BASE_2M', 0.0)
    base_3m = config['constantes'].get('UMIDADE_BASE_3M', 0.0)

    status_chuva_txt_pdf, _ = processamento.definir_status_chuva(ultima_chuva_pdf)
    status_umid_txt_pdf, _, _ = processamento.definir_status_umidade_hierarquico(
        umidade_1m_pdf, umidade_2m_pdf, umidade_3m_pdf, base_1m, base_2m, base_3m
    )

    risco_chuva_pdf = RISCO.get(status_chuva_txt_pdf, -1)
    risco_umidade_pdf = RISCO.get(status_umid_txt_pdf, -1)
    risco_geral_pdf = max(risco_chuva_pdf, risco_umidade_pdf)
    status_geral_pdf_texto, status_geral_pdf_cor = mapa_status_cor_geral.get(risco_geral_pdf,
                                                                             ("INDEFINIDO", "secondary"))

    # Cria figuras para PDF (usa strings formatadas)
    df_periodo_plot = df_periodo.copy();
    df_chuva_72h_plot = df_chuva_72h_pdf.copy()
    formato_data_pdf = '%d/%m/%y %Hh';
    df_periodo_plot['timestamp_str'] = df_periodo_plot['timestamp'].dt.strftime(formato_data_pdf);
    df_chuva_72h_plot['timestamp_str'] = df_chuva_72h_plot['timestamp'].dt.strftime(formato_data_pdf)
    fig_chuva_pdf = make_subplots(specs=[[{"secondary_y": True}]]);
    fig_chuva_pdf.add_trace(
        go.Bar(x=df_periodo_plot['timestamp_str'], y=df_periodo_plot['chuva_mm'], name='Pluv. Horária',
               marker_color='#2C3E50'), secondary_y=False);
    fig_chuva_pdf.add_trace(
        go.Scatter(x=df_chuva_72h_plot['timestamp_str'], y=df_chuva_72h_plot['chuva_mm'], name='Acumulada (72h)',
                   mode='lines', line=dict(color='#007BFF')), secondary_y=True)
    df_umidade_pdf_melted = df_periodo_plot.melt(id_vars=['timestamp_str'],
                                                 value_vars=['umidade_1m_perc', 'umidade_2m_perc', 'umidade_3m_perc'],
                                                 var_name='Sensor', value_name='Umidade (%)')
    fig_umidade_pdf = px.line(df_umidade_pdf_melted, x='timestamp_str', y='Umidade (%)', color='Sensor',
                              title="Umidade do Solo - Período Selecionado", color_discrete_map=CORES_UMIDADE)
    fig_umidade_pdf.update_traces(line=dict(width=3))
    fig_chuva_pdf.update_layout(title_text="Pluviometria - Período Selecionado", template=TEMPLATE_GRAFICO_MODERNO,
                                legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
                                yaxis_title="Pluv. Horária (mm)", yaxis2_title="Acumulada (mm)", xaxis_title=None,
                                xaxis_tickangle=-45, margin=dict(b=80))
    fig_chuva_pdf.update_yaxes(title_text="Pluv. Horária (mm)", secondary_y=False);
    fig_chuva_pdf.update_yaxes(title_text="Acumulada (mm)", secondary_y=True)
    fig_umidade_pdf.update_layout(template=TEMPLATE_GRAFICO_MODERNO,
                                  legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
                                  xaxis_title=None, xaxis_tickangle=-45, margin=dict(b=80))

    # Geração do PDF
    pdf_bytes = gerador_pdf.criar_relatorio_em_memoria(df_periodo, fig_chuva_pdf, fig_umidade_pdf,
                                                       status_geral_pdf_texto, status_geral_pdf_cor)
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    nome_arquivo = f"relatorio_{id_ponto}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return dict(content=pdf_base64, filename=nome_arquivo, type="application/pdf", base64=True)