# pages/map_view.py (ZOOM ALTERADO PARA 13 - Foco Intermediário)

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import pandas as pd
from io import StringIO
import traceback
import numpy as np # Import numpy

# Importa o app central e helpers
from app import app
# Importa constantes padrão para fallback em create_km_block
from data_source import PONTOS_DE_ANALISE, CONSTANTES_PADRAO
import processamento


# --- Layout da Página do Mapa ---
def get_layout():
    # ... (código mantido idêntico) ...
    print("Executando map_view.get_layout() (Dois Cards Superiores)")
    try:
        layout = dbc.Container([
            # Linha Título/Botão Removida conforme solicitado anteriormente
            dbc.Row([dbc.Col(
                html.Div([
                    dl.Map(
                        # Zoom alterado de 12 para 13 (nível intermediário)
                        id='mapa-principal', center=[-23.5951, -45.4438], zoom=13,
                        children=[
                            dl.TileLayer(),
                            dl.LayerGroup(id='map-pins-layer'), # Camada para pinos padrão
                            dbc.Card([dbc.CardHeader("KM 74 & KM 81", className="text-center small py-1"),
                                      dbc.CardBody(id='map-summary-left-content', children=[dbc.Spinner(size="sm")])],
                                     className="map-summary-card map-summary-left"),
                            dbc.Card([dbc.CardHeader("KM 67 & KM 72", className="text-center small py-1"),
                                      dbc.CardBody(id='map-summary-right-content', children=[dbc.Spinner(size="sm")])],
                                     className="map-summary-card map-summary-right")
                        ],
                        style={'width': '100%', 'height': '80vh', 'min-height': '600px'}
                    ),
                ], style={'position': 'relative'}),
                width=12, className="mb-4")])
        ], fluid=True)
        print("Layout do mapa (Dois Cards) criado com sucesso.")
        return layout
    except Exception as e:
        print(f"ERRO CRÍTICO em map_view.get_layout: {e}"); traceback.print_exc(); return html.Div(
            [html.H1("Erro Layout Mapa"), html.Pre(traceback.format_exc())])


# Callback 1: Atualiza os Pinos no mapa (Pinos padrão)
@app.callback(Output('map-pins-layer', 'children'), Input('store-dados-sessao', 'data'))
def update_map_pins(dados_json):
    # ... (código mantido idêntico - pinos padrão) ...
    if not dados_json: return dash.no_update
    try:
        df_completo = pd.read_json(StringIO(dados_json), orient='split'); df_completo['timestamp'] = pd.to_datetime(
            df_completo['timestamp'])
    except Exception:
        print("Callback Pinos: Erro JSON."); return []
    pinos_do_mapa = []
    for id_ponto, config in PONTOS_DE_ANALISE.items():
        df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
        if df_ponto.empty: continue
        ultima_chuva_72h_pino = 0.0
        try:
            df_chuva_72h_pino = processamento.calcular_acumulado_72h(df_ponto);
            if not df_chuva_72h_pino.empty:
                 ultima_chuva_72h_pino = df_chuva_72h_pino.iloc[-1]['chuva_mm']
                 if pd.isna(ultima_chuva_72h_pino): ultima_chuva_72h_pino = 0.0
        except Exception as e:
             print(f"Erro cálculo chuva pino {id_ponto}: {e}");
             ultima_chuva_72h_pino = 0.0
        pino = dl.Marker(
            position=config['lat_lon'],
            children=[
                dl.Tooltip(config['nome']),
                dl.Popup([
                    html.H5(config['nome']),
                    html.P(f"Chuva (72h): {ultima_chuva_72h_pino:.1f} mm"),
                    dbc.Button("Ver Dashboard", href=f"/ponto/{id_ponto}", size="sm", color="primary")
                ])
            ]
        )
        pinos_do_mapa.append(pino)
    return pinos_do_mapa


# --- Funções e Constantes para Callbacks 2a e 2b ---
CHUVA_LIMITE_VERDE = 50.0; CHUVA_LIMITE_AMARELO = 69.0; CHUVA_LIMITE_LARANJA = 89.0
def get_color_class_chuva(value):
    # ... (código mantido idêntico) ...
    if pd.isna(value): return "bg-secondary";
    if value <= CHUVA_LIMITE_VERDE: return "bg-success";
    elif value <= CHUVA_LIMITE_AMARELO: return "bg-warning";
    elif value <= CHUVA_LIMITE_LARANJA: return "bg-orange";
    else: return "bg-danger"

RISCO_MAP = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3, "SEM DADOS": -1, "ERRO": -1}

# --- Função auxiliar create_km_block (Mantida) ---
def create_km_block(id_ponto, config, df_ponto):
    ultima_chuva_72h = 0.0;
    umidade_1m_atual = 0.0; umidade_2m_atual = 0.0; umidade_3m_atual = 0.0
    constantes_ponto = config.get('constantes', CONSTANTES_PADRAO)
    base_1m = constantes_ponto.get('UMIDADE_BASE_1M', CONSTANTES_PADRAO['UMIDADE_BASE_1M'])
    base_2m = constantes_ponto.get('UMIDADE_BASE_2M', CONSTANTES_PADRAO['UMIDADE_BASE_2M'])
    base_3m = constantes_ponto.get('UMIDADE_BASE_3M', CONSTANTES_PADRAO['UMIDADE_BASE_3M'])
    # saturacao = constantes_ponto.get('UMIDADE_SATURACAO', CONSTANTES_PADRAO['UMIDADE_SATURACAO']) # Não é mais necessário para a barra
    status_chuva_txt, status_chuva_col = "SEM DADOS", "secondary"
    status_umid_txt, status_umid_col, cor_umidade_class = "SEM DADOS", "secondary", "bg-secondary"

    try:
        if not df_ponto.empty:
            df_chuva_72h = processamento.calcular_acumulado_72h(df_ponto)
            if not df_chuva_72h.empty:
                chuva_val = df_chuva_72h.iloc[-1]['chuva_mm']
                if not pd.isna(chuva_val):
                    ultima_chuva_72h = chuva_val
                    status_chuva_txt, status_chuva_col = processamento.definir_status_chuva(ultima_chuva_72h)
            try:
                ultimo_dado = df_ponto.iloc[-1]
                umidade_1m_atual = ultimo_dado.get('umidade_1m_perc', base_1m);
                umidade_2m_atual = ultimo_dado.get('umidade_2m_perc', base_2m);
                umidade_3m_atual = ultimo_dado.get('umidade_3m_perc', base_3m)
                if pd.isna(umidade_1m_atual): umidade_1m_atual = base_1m
                if pd.isna(umidade_2m_atual): umidade_2m_atual = base_2m
                if pd.isna(umidade_3m_atual): umidade_3m_atual = base_3m
            except IndexError: pass
            # Chama processamento para obter o STATUS (LIVRE, ATENÇÃO, etc.)
            status_umid_txt, status_umid_col, cor_umidade_class = processamento.definir_status_umidade_hierarquico(
                umidade_1m_atual, umidade_2m_atual, umidade_3m_atual, base_1m, base_2m, base_3m
            )
    except Exception as e:
        print(f"ERRO GERAL em create_km_block para {id_ponto}: {e}")
        ultima_chuva_72h = 0.0; status_chuva_txt = "ERRO"; status_chuva_col = "danger"
        status_umid_txt, status_umid_col, cor_umidade_class = "ERRO", "danger", "bg-danger"

    cor_chuva_class = get_color_class_chuva(ultima_chuva_72h)
    chuva_max_visual = 90.0
    chuva_percent = max(0, min(100, (ultima_chuva_72h / chuva_max_visual) * 100))

    # --- Lógica: Calcular altura da barra de umidade com NÍVEIS FIXOS ---
    umidade_percent_realista = 0 # Default para SEM DADOS ou ERRO
    risco_umidade = RISCO_MAP.get(status_umid_txt, -1) # Usa status padrão (ATENÇÃO, etc)

    if risco_umidade == 0: # LIVRE
        umidade_percent_realista = 25
    elif risco_umidade == 1: # ATENÇÃO
        umidade_percent_realista = 50
    elif risco_umidade == 2: # ALERTA
        umidade_percent_realista = 75
    elif risco_umidade == 3: # PARALIZAÇÃO
        umidade_percent_realista = 100
    # else: SEM DADOS/ERRO -> 0%
    # --- FIM DA LÓGICA ---


    chuva_gauge = html.Div( # Gauge Chuva
        [
            html.Div(className=f"gauge-bar {cor_chuva_class}", style={'height': f'{chuva_percent}%'}),
            html.Div(
                [html.Span(f"{ultima_chuva_72h:.0f}"), html.Br(), html.Span("mm", style={'fontSize': '0.8em'})],
                className="gauge-label", style={'fontSize': '2.5em', 'lineHeight': '1.1'}
            )
        ], className="gauge-vertical-container"
    )
    umidade_gauge = html.Div( # Gauge Umidade
        [html.Div(className=f"gauge-bar {cor_umidade_class}", style={'height': f'{umidade_percent_realista}%'})],
        className="gauge-vertical-container"
    )
    chuva_badge = dbc.Badge(status_chuva_txt, color=status_chuva_col, className="w-100 mt-1 small badge-black-text")
    umidade_badge = dbc.Badge(status_umid_txt, color=status_umid_col, className="w-100 mt-1 small badge-black-text")

    # Envolve com Link (mantido)
    link_destino = f"/ponto/{id_ponto}"
    conteudo_bloco = html.Div([
        html.H6(config['nome'], className="text-center mb-1"),
        dbc.Row([
            dbc.Col([html.Div("Chuva (72h)", className="small text-center"), chuva_gauge, chuva_badge], width=6),
            dbc.Col([html.Div("Umidade", className="small text-center"), umidade_gauge, umidade_badge], width=6),
        ], className="g-0"),
    ], className="km-summary-block")

    return html.A(
        conteudo_bloco,
        href=link_destino,
        style={'textDecoration': 'none', 'color': 'inherit'}
    )


# --- Callbacks 2a e 2b (Callbacks que USAM create_km_block) ---
# (Mantidos idênticos)
@app.callback(Output('map-summary-left-content', 'children'), Input('store-dados-sessao', 'data'))
def update_summary_left(dados_json):
    # ... (código com try/except mantido) ...
    if not dados_json: return dbc.Spinner(size="sm")
    try:
        df_completo = pd.read_json(StringIO(dados_json), orient='split'); df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
        left_blocks = []
        ids_esquerda = ["Ponto-C-KM74", "Ponto-D-KM81"]
        for id_ponto in ids_esquerda:
            if id_ponto in PONTOS_DE_ANALISE:
                config = PONTOS_DE_ANALISE[id_ponto]
                df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
                km_block = create_km_block(id_ponto, config, df_ponto)
                left_blocks.append(km_block)
        return left_blocks if left_blocks else dbc.Alert("Dados indisponíveis (L).", color="warning", className="m-2 small")
    except Exception as e:
        print(f"ERRO GERAL em update_summary_left: {e}")
        return dbc.Alert(f"Erro ao carregar dados (L): {e}", color="danger", className="m-2 small")

@app.callback(Output('map-summary-right-content', 'children'), Input('store-dados-sessao', 'data'))
def update_summary_right(dados_json):
    # ... (código com try/except mantido) ...
    if not dados_json: return dbc.Spinner(size="sm")
    try:
        df_completo = pd.read_json(StringIO(dados_json), orient='split'); df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
        right_blocks = []
        ids_direita = ["Ponto-A-KM67", "Ponto-B-KM72"]
        for id_ponto in ids_direita:
            if id_ponto in PONTOS_DE_ANALISE:
                config = PONTOS_DE_ANALISE[id_ponto]
                df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
                km_block = create_km_block(id_ponto, config, df_ponto)
                right_blocks.append(km_block)
        return right_blocks if right_blocks else dbc.Alert("Dados indisponíveis (R).", color="warning", className="m-2 small")
    except Exception as e:
        print(f"ERRO GERAL em update_summary_right: {e}")
        return dbc.Alert(f"Erro ao carregar dados (R): {e}", color="danger", className="m-2 small")
# --- FIM DOS CALLBACKS ---