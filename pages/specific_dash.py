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
from data_source import PONTOS_DE_ANALISE, CONSTANTES_PADRAO, FREQUENCIA_SIMULACAO
import processamento
import gerador_pdf

# --- Mapas de Cores e Riscos ---
CORES_ALERTAS_CSS = {
    "verde": "green",
    "amarelo": "#FFD700",  # Amarelo Ouro
    "laranja": "#fd7e14",
    "vermelho": "#dc3545",
    "cinza": "grey"
}
CORES_UMIDADE = {
    '1m': CORES_ALERTAS_CSS["verde"],
    '2m': CORES_ALERTAS_CSS["amarelo"],  # Amarelo Ouro
    '3m': CORES_ALERTAS_CSS["vermelho"]
}

RISCO = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3, "SEM DADOS": -1, "INDEFINIDO": -1}
mapa_status_cor_geral = {
    0: ("LIVRE", "success"),
    1: ("ATENÇÃO", "warning"),
    2: ("ALERTA", "orange"),
    3: ("PARALIZAÇÃO", "danger"),
    -1: ("SEM DADOS", "secondary")
}


# --- Layout da Página Específica ---
def get_layout():
    opcoes_tempo = [{'label': f'Últimas {h} horas', 'value': h} for h in [1, 3, 6, 12, 18, 24, 72, 84, 96]] + [
        {'label': 'Todo o Histórico', 'value': 14 * 24}]
    return dbc.Container([
        dcc.Store(id='store-id-ponto-ativo'),

        # --- TÍTULO DA ESTAÇÃO (Centralizado) ---
        html.Div(id='specific-dash-title', className="my-3 text-center"),
        # --- FIM NOVO ---

        dbc.Row(id='specific-dash-cards', children=[dbc.Spinner(size="lg")]),
        dbc.Row([dbc.Col(dbc.Label("Período (Gráficos):"), width="auto"), dbc.Col(
            dcc.Dropdown(id='graph-time-selector', options=opcoes_tempo, value=72, clearable=False, searchable=False),
            width=12, lg=4)], align="center", className="my-3"),
        dbc.Row(id='specific-dash-graphs', children=[dbc.Spinner(size="lg")], className="my-4"),
        dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([
            dcc.DatePickerRange(id='pdf-date-picker', start_date=(
                    pd.Timestamp.now() - pd.Timedelta(days=7)).date(),
                                end_date=pd.Timestamp.now().date(),
                                display_format='DD/MM/YYYY', className="mb-3"),
            html.Br(),
            dcc.Loading(id="loading-pdf", type="default", children=[
                html.Div([dbc.Button("Gerar e Baixar PDF", id='btn-pdf-especifico', color="primary", size="lg"),
                          dcc.Download(id='download-pdf-especifico')])])
        ]), className="shadow-sm text-center"),
            className="mb-5")]),
    ], fluid=True)


# --- Callbacks da Página Específica ---

# Callback para definir o TÍTULO (Estação KM)
@app.callback(
    Output('specific-dash-title', 'children'),
    Input('url', 'pathname')
)
def update_specific_title(pathname):
    if not pathname.startswith('/ponto/'):
        return dash.no_update

    try:
        id_ponto = pathname.split('/')[-1]
        config = PONTOS_DE_ANALISE.get(id_ponto, {"nome": "Ponto Desconhecido"})

        # --- ALTERAÇÃO: Título centralizado, cor preta e removendo o ID técnico ---
        nome_km = config['nome']  # Ex: "KM 67"
        nome_estacao_formatado = f"Estação {nome_km}"

        return html.H3(nome_estacao_formatado,
                       style={'color': '#000000', 'font-weight': 'bold'})
        # --- FIM DA ALTERAÇÃO ---

    except Exception:
        return html.H3("Detalhes da Estação", style={'color': '#000000', 'font-weight': 'bold'})


# Callback 1: Atualiza o dashboard
@app.callback(
    [
        Output('specific-dash-cards', 'children'),
        Output('specific-dash-graphs', 'children'),
        Output('store-id-ponto-ativo', 'data')
    ],
    [
        Input('url', 'pathname'),
        Input('store-dados-sessao', 'data'),
        Input('graph-time-selector', 'value')
    ]
)
def update_specific_dashboard(pathname, dados_json, selected_hours):
    if not dados_json or not pathname.startswith('/ponto/') or selected_hours is None:
        return dash.no_update, dash.no_update, dash.no_update
    id_ponto = "";
    config = {}
    try:
        id_ponto = pathname.split('/')[-1];
        config = PONTOS_DE_ANALISE[id_ponto]
    except KeyError:
        return "Ponto não encontrado", "Erro: Ponto inválido.", None
    constantes_ponto = config.get('constantes', CONSTANTES_PADRAO)

    # Lendo as chaves de base e saturação individuais (corrigido do KeyError anterior)
    base_1m = constantes_ponto.get('UMIDADE_BASE_1M', CONSTANTES_PADRAO['UMIDADE_BASE_1M'])
    base_2m = constantes_ponto.get('UMIDADE_BASE_2M', CONSTANTES_PADRAO['UMIDADE_BASE_2M'])
    base_3m = constantes_ponto.get('UMIDADE_BASE_3M', CONSTANTES_PADRAO['UMIDADE_BASE_3M'])

    saturacao_1m = constantes_ponto.get('UMIDADE_SATURACAO_1M', CONSTANTES_PADRAO.get('UMIDADE_SATURACAO_1M', 45.0))
    saturacao_2m = constantes_ponto.get('UMIDADE_SATURACAO_2M', CONSTANTES_PADRAO.get('UMIDADE_SATURACAO_2M', 45.0))
    saturacao_3m = constantes_ponto.get('UMIDADE_SATURACAO_3M', CONSTANTES_PADRAO.get('UMIDADE_SATURACAO_3M', 45.0))

    df_completo = pd.read_json(StringIO(dados_json), orient='split');
    df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
    df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
    if df_ponto.empty: return "Sem dados.", "", id_ponto
    df_chuva_72h = processamento.calcular_acumulado_72h(df_ponto)
    if df_chuva_72h.empty: return "Calculando...", "", id_ponto
    try:
        ultimo_dado = df_ponto.iloc[-1]
        ultima_chuva_72h = df_chuva_72h.iloc[-1]['chuva_mm'] if not df_chuva_72h.empty else None
        umidade_1m_atual = ultimo_dado.get('umidade_1m_perc', None)
        umidade_2m_atual = ultimo_dado.get('umidade_2m_perc', None)
        umidade_3m_atual = ultimo_dado.get('umidade_3m_perc', None)
        if pd.isna(ultima_chuva_72h): ultima_chuva_72h = 0.0
        if pd.isna(umidade_1m_atual): umidade_1m_atual = base_1m
        if pd.isna(umidade_2m_atual): umidade_2m_atual = base_2m
        if pd.isna(umidade_3m_atual): umidade_3m_atual = base_3m
    except IndexError:
        return "Dados insuficientes.", "", id_ponto

    # 1. Status Chuva
    status_chuva_txt, status_chuva_col = processamento.definir_status_chuva(ultima_chuva_72h)
    risco_chuva = RISCO.get(status_chuva_txt, -1)

    # 2. Status GERAL Umidade (Fluxograma)
    status_umid_txt, status_umid_col_bootstrap, _ = processamento.definir_status_umidade_hierarquico(
        umidade_1m_atual, umidade_2m_atual, umidade_3m_atual, base_1m, base_2m, base_3m
    )
    risco_umidade = RISCO.get(status_umid_txt, -1)

    # 3. Status GERAL (Max(Chuva, Umidade))
    risco_geral = max(risco_chuva, risco_umidade)

    # 4. Texto e Cor do Status Geral
    status_geral_texto, status_geral_cor_bootstrap = mapa_status_cor_geral.get(risco_geral, ("INDEFINIDO", "secondary"))

    # Aplica a classe CSS para a cor de fundo do card
    if status_geral_cor_bootstrap == "warning":
        card_class_color = "bg-warning"
    elif status_geral_cor_bootstrap == "orange":
        card_class_color = "bg-orange"
    elif status_geral_cor_bootstrap == "danger":
        card_class_color = "bg-danger"
    else:
        card_class_color = "bg-" + status_geral_cor_bootstrap  # bg-success, bg-secondary, etc.

    # 5. Cores Individuais para Card de Umidade
    DELTA_TRIGGER_UMIDADE = 5.0

    css_color_s1 = CORES_ALERTAS_CSS["amarelo"] if (umidade_1m_atual - base_1m) >= DELTA_TRIGGER_UMIDADE else \
    CORES_ALERTAS_CSS["verde"]
    css_color_s2 = CORES_ALERTAS_CSS["laranja"] if (umidade_2m_atual - base_2m) >= DELTA_TRIGGER_UMIDADE else \
    CORES_ALERTAS_CSS["verde"]
    css_color_s3 = CORES_ALERTAS_CSS["vermelho"] if (umidade_3m_atual - base_3m) >= DELTA_TRIGGER_UMIDADE else \
    CORES_ALERTAS_CSS["verde"]

    # Layout dos Cards (Corrigido para usar style inline)
    layout_cards = [
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H5("Status Atual", style={'color': '#000000', 'font-weight': 'bold'}),
            html.P(status_geral_texto, className="fs-3", style={'color': '#000000', 'font-weight': 'bold'})
        ]),
            className=f"shadow h-100 {card_class_color}",  # Usa a classe de fundo
        ), xs=12, md=4, className="mb-4"),
        dbc.Col(dbc.Card(
            dbc.CardBody([html.H5("Chuva 72h"), html.P(f"{ultima_chuva_72h:.1f} mm", className="fs-3 fw-bold")]),
            className="shadow h-100 bg-white"), xs=12, md=4, className="mb-4"),
        dbc.Col(dbc.Card(
            dbc.CardBody([
                html.H5("Umidade (%)", className="mb-3"),
                dbc.Row([
                    dbc.Col(
                        html.P([
                            html.Span(f"{umidade_1m_atual:.1f}", className="fs-3 fw-bold",
                                      style={'color': css_color_s1}),
                            html.Span(" (1m)", className="small", style={'color': css_color_s1})
                        ], className="mb-0 text-center"),
                        width=4
                    ),
                    dbc.Col(
                        html.P([
                            html.Span(f"{umidade_2m_atual:.1f}", className="fs-3 fw-bold",
                                      style={'color': css_color_s2}),
                            html.Span(" (2m)", className="small", style={'color': css_color_s2})
                        ], className="mb-0 text-center"),
                        width=4
                    ),
                    dbc.Col(
                        html.P([
                            html.Span(f"{umidade_3m_atual:.1f}", className="fs-3 fw-bold",
                                      style={'color': css_color_s3}),
                            html.Span(" (3m)", className="small", style={'color': css_color_s3})
                        ], className="mb-0 text-center"),
                        width=4
                    ),
                ], justify="around")
            ]),
            className="shadow h-100 bg-white"), xs=12, md=4, className="mb-4"),
    ]

    # Filtra dados para gráficos
    PONTOS_POR_HORA = int(60 / (FREQUENCIA_SIMULACAO.total_seconds() / 60))
    n_pontos_desejados = selected_hours * PONTOS_POR_HORA
    n_pontos_plot = min(n_pontos_desejados, len(df_ponto))
    df_ponto_plot = df_ponto.tail(n_pontos_plot);
    df_chuva_72h_plot = processamento.calcular_acumulado_72h(df_ponto).tail(n_pontos_plot)
    n_horas_titulo = selected_hours

    # Gráfico de Chuva (Mantido)
    fig_chuva = make_subplots(specs=[[{"secondary_y": True}]])
    fig_chuva.add_trace(
        go.Bar(x=df_ponto_plot['timestamp'], y=df_ponto_plot['chuva_mm'], name='Pluviometria Horária (mm)',
               marker_color='#2C3E50', opacity=0.8), secondary_y=False)
    fig_chuva.add_trace(go.Scatter(x=df_chuva_72h_plot['timestamp'], y=df_chuva_72h_plot['chuva_mm'],
                                   name='Precipitação Acumulada (mm)', mode='lines',
                                   line=dict(color='#007BFF', width=2.5)), secondary_y=True)
    fig_chuva.update_layout(title_text=f"Pluviometria - {config['nome']} ({n_horas_titulo}h)",
                            template=TEMPLATE_GRAFICO_MODERNO,
                            margin=dict(l=40, r=20, t=50, b=40),
                            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor='center', x=0.5),
                            xaxis_title="Data e Hora", yaxis_title="Pluviometria Horária (mm)",
                            yaxis2_title="Precipitação Acumulada (mm)", hovermode="x unified", bargap=0.1)
    fig_chuva.update_yaxes(title_text="Pluviometria Horária (mm)", secondary_y=False);
    fig_chuva.update_yaxes(title_text="Acumulada (mm)", secondary_y=True)

    # Gráfico de Umidade
    df_umidade = df_ponto_plot.melt(id_vars=['timestamp'],
                                    value_vars=['umidade_1m_perc', 'umidade_2m_perc', 'umidade_3m_perc'],
                                    var_name='Sensor', value_name='Umidade (%)')

    df_umidade['Sensor'] = df_umidade['Sensor'].replace({
        'umidade_1m_perc': '1m',
        'umidade_2m_perc': '2m',
        'umidade_3m_perc': '3m'
    })

    fig_umidade = px.line(df_umidade, x='timestamp', y='Umidade (%)', color='Sensor',
                          title=f"Variação da Umidade - {config['nome']} ({n_horas_titulo}h)",
                          color_discrete_map=CORES_UMIDADE)  # Usa mapa de cores
    fig_umidade.update_traces(line=dict(width=3));
    fig_umidade.update_layout(template=TEMPLATE_GRAFICO_MODERNO, margin=dict(l=40, r=20, t=40, b=50),
                              legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))

    layout_graficos = [
        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_chuva)), className="shadow-sm"), width=12, className="mb-4"),
        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_umidade)), className="shadow-sm"), width=12,
                className="mb-4"), ]

    return layout_cards, layout_graficos, id_ponto


# Callback 2: Gerar o PDF (Mantido)
@app.callback(
    Output('download-pdf-especifico', 'data'),
    Input('btn-pdf-especifico', 'n_clicks'),
    [State('pdf-date-picker', 'start_date'), State('pdf-date-picker', 'end_date'),
     State('store-id-ponto-ativo', 'data'), State('store-dados-sessao', 'data')]
)
def gerar_download_pdf_especifico(n_clicks, start_date_str, end_date_str, id_ponto, dados_json):
    if not n_clicks or not id_ponto or not dados_json: return dash.no_update

    try:
        config = PONTOS_DE_ANALISE[id_ponto]
    except KeyError:
        print("Erro PDF: id_ponto não encontrado");
        return dash.no_update

    # Lendo as chaves de base e saturação individuais (corrigido do KeyError anterior)
    constantes_ponto = config.get('constantes', CONSTANTES_PADRAO)
    base_1m = constantes_ponto.get('UMIDADE_BASE_1M', CONSTANTES_PADRAO['UMIDADE_BASE_1M'])
    base_2m = constantes_ponto.get('UMIDADE_BASE_2M', CONSTANTES_PADRAO['UMIDADE_BASE_2M'])
    base_3m = constantes_ponto.get('UMIDADE_BASE_3M', CONSTANTES_PADRAO['UMIDADE_BASE_3M'])
    saturacao_1m = constantes_ponto.get('UMIDADE_SATURACAO_1M', CONSTANTES_PADRAO.get('UMIDADE_SATURACAO_1M', 45.0))
    saturacao_2m = constantes_ponto.get('UMIDADE_SATURACAO_2M', CONSTANTES_PADRAO.get('UMIDADE_SATURACAO_2M', 45.0))
    saturacao_3m = constantes_ponto.get('UMIDADE_SATURACAO_3M', CONSTANTES_PADRAO.get('UMIDADE_SATURACAO_3M', 45.0))

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
    df_chuva_72h_pdf = processamento.calcular_acumulado_72h(df_periodo)
    if df_chuva_72h_pdf.empty: print("Sem chuva período PDF."); return dash.no_update
    try:
        ultimo_dado_pdf = df_periodo.iloc[-1]
        ultima_chuva_pdf = df_chuva_72h_pdf.iloc[-1]['chuva_mm'] if not df_chuva_72h_pdf.empty else None
        umidade_1m_pdf = ultimo_dado_pdf.get('umidade_1m_perc', None)
        umidade_2m_pdf = ultimo_dado_pdf.get('umidade_2m_perc', None)
        umidade_3m_pdf = ultimo_dado_pdf.get('umidade_3m_perc', None)
        if pd.isna(ultima_chuva_pdf): ultima_chuva_pdf = 0.0
        if pd.isna(umidade_1m_pdf): umidade_1m_pdf = base_1m
        if pd.isna(umidade_2m_pdf): umidade_2m_pdf = base_2m
        if pd.isna(umidade_3m_pdf): umidade_3m_pdf = base_3m
    except IndexError:
        print("Erro PDF: Dados insuficientes para iloc[-1].");
        return dash.no_update

    status_chuva_txt_pdf, _ = processamento.definir_status_chuva(ultima_chuva_pdf)
    status_umid_txt_pdf, _, _ = processamento.definir_status_umidade_hierarquico(
        umidade_1m_pdf, umidade_2m_pdf, umidade_3m_pdf, base_1m, base_2m, base_3m
    )
    risco_umidade_pdf = RISCO.get(status_umid_txt_pdf, -1)
    risco_chuva_pdf = RISCO.get(status_chuva_txt_pdf, -1)
    risco_geral_pdf = max(risco_chuva_pdf, risco_umidade_pdf)
    status_geral_pdf_texto, status_geral_pdf_cor = mapa_status_cor_geral.get(risco_geral_pdf,
                                                                             ("INDEFINIDO", "secondary"))
    if risco_umidade_pdf > 0 and risco_umidade_pdf >= risco_chuva_pdf:
        status_geral_pdf_texto, status_geral_pdf_cor, _ = processamento.STATUS_MAP_HIERARQUICO[risco_umidade_pdf]

    # Cria figuras para PDF
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

    df_umidade_pdf_melted['Sensor'] = df_umidade_pdf_melted['Sensor'].replace({
        'umidade_1m_perc': '1m',
        'umidade_2m_perc': '2m',
        'umidade_3m_perc': '3m'
    })

    fig_umidade_pdf = px.line(df_umidade_pdf_melted, x='timestamp_str', y='Umidade (%)', color='Sensor',
                              title="Umidade do Solo - Período Selecionado",
                              color_discrete_map=CORES_UMIDADE)  # Usa novo mapa de cores
    fig_umidade_pdf.update_traces(line=dict(width=3))

    # Ajuste da legenda do PDF (Mantido da última correção)
    fig_chuva_pdf.update_layout(title_text="Pluviometria - Período Selecionado", template=TEMPLATE_GRAFICO_MODERNO,
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                                yaxis_title="Pluv. Horária (mm)", yaxis2_title="Acumulada (mm)", xaxis_title=None,
                                xaxis_tickangle=-45,
                                margin=dict(b=80, t=80))
    fig_chuva_pdf.update_yaxes(title_text="Pluv. Horária (mm)", secondary_y=False);
    fig_chuva_pdf.update_yaxes(title_text="Acumulada (mm)", secondary_y=True)

    fig_umidade_pdf.update_layout(template=TEMPLATE_GRAFICO_MODERNO,
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                                  xaxis_title=None, xaxis_tickangle=-45,
                                  margin=dict(b=80, t=80))

    # Geração do PDF
    pdf_bytes = gerador_pdf.criar_relatorio_em_memoria(df_periodo, fig_chuva_pdf, fig_umidade_pdf,
                                                       status_geral_pdf_texto, status_geral_pdf_cor)
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    nome_arquivo = f"relatorio_{id_ponto}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return dict(content=pdf_base64, filename=nome_arquivo, type="application/pdf", base64=True)

