# index.py (CORRIGIDO - Removido o dcc.Interval para permitir o "sleep" no Render)

import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
from io import StringIO
import os
import json

# Importa as páginas e o app central
from app import app, server
from pages import map_view, general_dash, specific_dash
from data_source import PONTOS_DE_ANALISE
import processamento
import alertas


# --- Layout da Barra de Navegação (Mantido) ---
def get_navbar():
    logo_riskgeo_path = app.get_asset_url('LogoMarca RiskGeo Solutions.PNG')
    logo_tamoios_path = app.get_asset_url('tamoios.PNG')
    cor_fundo_navbar = '#003366'
    navbar = dbc.Navbar(
        dbc.Container(
            [dbc.Row([
                dbc.Col(html.A(html.Img(src=logo_tamoios_path, height="52px"), href="/"), width="auto",
                        className="me-auto"),
                dbc.Col(html.H4("SISTEMA DE MONITORAMENTO TAMOIOS", className="mb-0 text-center",
                                style={'fontWeight': 'bold', 'color': 'white'}), width="auto"),
                dbc.Col(dbc.Row([
                    dbc.Col(dbc.Nav([
                        dbc.NavItem(dbc.NavLink("Mapa Geral", href="/", active="exact", className="text-light")),
                        dbc.NavItem(dbc.NavLink("Dashboard Geral", href="/dashboard-geral", active="exact",
                                                className="text-light")),
                    ], navbar=True, className="flex-nowrap"), width="auto"),
                    dbc.Col(html.Img(src=logo_riskgeo_path, height="52px", className="ms-3"), width="auto"),
                ], align="center", className="g-0 flex-nowrap", ), width="auto", className="ms-auto"),
            ], align="center", className="w-100 flex-nowrap", ),
            ], fluid=True),
        style={'backgroundColor': cor_fundo_navbar}, dark=True, className="mb-4"
    )
    return navbar


# --- Layout Principal da Aplicação (Mantido) ---
RISCO = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3, "SEM DADOS": -1, "INDEFINIDO": -1}
mapa_status_cor_geral = {0: ("LIVRE", "success"), 1: ("ATENÇÃO", "warning"), 2: ("ALERTA", "orange"),
                         3: ("PARALIZAÇÃO", "danger"), -1: ("SEM DADOS", "secondary")}

# Variável Global para rastrear o ESTADO DE CHUVA (para evitar race condition)
ESTADO_ALERTA_SERVIDOR = {}

# --- INÍCIO DA ALTERAÇÃO (Remoção do Intervalo) ---
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),

    # Mantido 'memory' para evitar consumo de bandwidth
    dcc.Store(id='store-dados-sessao', storage_type='memory'),
    dcc.Store(id='store-ultimo-status', storage_type='memory'),  # Agora armazena o status da CHUVA

    # O dcc.Interval foi REMOVIDO para permitir que o Render "durma"
    # dcc.Interval(id='intervalo-atualizacao', interval=2 * 1000, n_intervals=0),

    get_navbar(),
    html.Div(id='page-content')
])


# --- FIM DA ALTERAÇÃO ---


# --- Callbacks ---

# Callback 1: O Roteador de Páginas (Mantido)
@app.callback(Output('page-content', 'children'), Input('url', 'pathname'))
def display_page(pathname):
    if pathname.startswith('/ponto/'):
        return specific_dash.get_layout()
    elif pathname == '/dashboard-geral':
        return general_dash.get_layout()
    else:
        return map_view.get_layout()


# Callback 2: Atualização de Dados (Background) - MODIFICADO
@app.callback(
    Output('store-dados-sessao', 'data'),
    Input('url', 'pathname')  # MUDANÇA: Acionado 1 vez no carregamento da página
)
def carregar_dados_em_background(pathname):
    import data_source
    # Esta função agora só roda UMA VEZ quando a página é aberta.
    print(f"Carregamento inicial de dados (Trigger: {pathname}): Buscando dados...")
    df = data_source.get_data();
    return df.to_json(date_format='iso', orient='split')


# Callback 3: Verificação de Alertas (Background) - (Baseado na CHUVA)
@app.callback(
    Output('store-ultimo-status', 'data'),  # Agora salva o status da CHUVA
    Input('store-dados-sessao', 'data'),  # Acionado após o Callback 2
    State('store-ultimo-status', 'data')  # Usado para inicializar a variável global
)
def verificar_alertas_em_background(dados_json, status_antigo_json_store):
    # Esta função agora só roda UMA VEZ, após o carregamento dos dados.

    global ESTADO_ALERTA_SERVIDOR

    if not dados_json:
        return dash.no_update

    try:
        df_completo = pd.read_json(StringIO(dados_json), orient='split')
        df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
    except Exception as e:
        print(f"Erro ao ler JSON em callback de alerta: {e}")
        return dash.no_update

    # --- Lógica de Sincronização (Mantida) ---
    if not ESTADO_ALERTA_SERVIDOR and status_antigo_json_store:
        try:
            ESTADO_ALERTA_SERVIDOR = json.loads(status_antigo_json_store)
            print(f"Sincronizando estado (CHUVA) do servidor com o dcc.Store: {ESTADO_ALERTA_SERVIDOR}")
        except Exception:
            ESTADO_ALERTA_SERVIDOR = {}

    status_novos_para_store = {}

    # 1. Loop para verificar status individual
    for id_ponto, config in PONTOS_DE_ANALISE.items():

        status_chuva_antigo_ponto = ESTADO_ALERTA_SERVIDOR.get(id_ponto, "INDEFINIDO")
        df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
        status_chuva_txt = "SEM DADOS"

        if not df_ponto.empty:
            try:
                df_chuva_72h = processamento.calcular_acumulado_72h(df_ponto)
                ultima_chuva_72h = df_chuva_72h.iloc[-1]['chuva_mm'] if not df_chuva_72h.empty and not pd.isna(
                    df_chuva_72h.iloc[-1]['chuva_mm']) else None
                status_chuva_txt, _ = processamento.definir_status_chuva(ultima_chuva_72h)
            except Exception as e_calc:
                print(f"Erro cálculo alerta para {id_ponto}: {e_calc}");
                status_chuva_txt = "ERRO"

        if status_chuva_txt != status_chuva_antigo_ponto:
            print(f"ALERTA (CHUVA): Ponto {id_ponto} mudou de {status_chuva_antigo_ponto} -> {status_chuva_txt}")
            ESTADO_ALERTA_SERVIDOR[id_ponto] = status_chuva_txt
            deve_enviar = False

            if status_chuva_txt == "PARALIZAÇÃO" and status_chuva_antigo_ponto == "ALERTA":
                deve_enviar = True
                print(">>> Transição CRÍTICA (CHUVA: ALERTA->PARALIZAÇÃO) detectada. Disparando alarme.")
            elif status_chuva_txt == "LIVRE" and status_chuva_antigo_ponto == "ATENÇÃO":
                deve_enviar = True
                print(">>> Transição de NORMALIZAÇÃO (CHUVA: ATENÇÃO->LIVRE) detectada. Disparando alarme.")

            if deve_enviar:
                try:
                    alertas.enviar_alerta(
                        id_ponto,
                        config.get('nome', id_ponto),
                        status_chuva_txt,
                        status_chuva_antigo_ponto
                    )
                except Exception as e:
                    print(f"AVISO: Falha na notificação para {id_ponto}. Erro: {e}")

            status_novos_para_store[id_ponto] = status_chuva_txt
        else:
            status_novos_para_store[id_ponto] = status_chuva_antigo_ponto

    return json.dumps(status_novos_para_store)


# --- SEÇÃO DE EXECUÇÃO LOCAL (Mantida) ---
if __name__ == '__main__':
    host = '127.0.0.1'
    port = 8050
    print("Inicializando servidor Dash...")
    print(f"Aplicação rodando em: http://{host}:{port}/")
    print("Clique no link acima.")
    app.run(debug=True, host=host, port=port)