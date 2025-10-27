# index.py (VERSÃO FINAL - Com Variável Global + use_reloader=False)

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
from data_source import PONTOS_DE_ANALISE, CONSTANTES_PADRAO
import processamento
import alertas
import data_source  # Importa o data_source diretamente


# --- Layout da Barra de Navegação (Mantido) ---
def get_navbar():
    # ... (código mantido idêntico) ...
    logo_riskgeo_path = app.get_asset_url('LogoMarca RiskGeo Solutions.PNG')
    logo_tamoios_path = app.get_asset_url('tamoios.PNG')
    cor_fundo_navbar = '#003366'
    nova_altura_logo = "60px"
    navbar = dbc.Navbar(
        dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Row(
                                [
                                    dbc.Col(html.A(html.Img(src=logo_tamoios_path, height=nova_altura_logo), href="/"),
                                            width="auto"),
                                    dbc.Col(html.Img(src=logo_riskgeo_path, height=nova_altura_logo, className="ms-3"),
                                            width="auto"),
                                ],
                                align="center",
                                className="g-0",
                            ),
                            width="auto",
                        ),
                        dbc.Col(
                            html.H4("SISTEMA DE MONITORAMENTO TAMOIOS", className="mb-0 text-center",
                                    style={'fontWeight': 'bold', 'color': 'white'}),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Nav(
                                [
                                    dbc.NavItem(
                                        dbc.NavLink("Mapa Geral", href="/", active="exact", className="text-light",
                                                    style={'font-size': '1.75rem', 'font-weight': '500'})),
                                    dbc.NavItem(dbc.NavLink("Dashboard Geral", href="/dashboard-geral", active="exact",
                                                            className="text-light ms-3",
                                                            style={'font-size': '1.75rem', 'font-weight': '500'})),
                                ],
                                navbar=True,
                                className="flex-nowrap",
                            ),
                            width="auto",
                        ),
                    ],
                    align="center",
                    className="w-100 flex-nowrap",
                    justify="between",
                ),
            ],
            fluid=True
        ),
        style={'backgroundColor': cor_fundo_navbar},
        dark=True,
        className="mb-4"
    )
    return navbar


# --- Layout Principal da Aplicação (Mantido) ---
RISCO = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3, "SEM DADOS": -1, "INDEFINIDO": -1}
mapa_status_cor_geral = {0: ("LIVRE", "success"), 1: ("ATENÇÃO", "warning"), 2: ("ALERTA", "orange"),
                         3: ("PARALIZAÇÃO", "danger"), -1: ("SEM DADOS", "secondary")}

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='store-dados-sessao', storage_type='session'),
    dcc.Store(id='store-ultimo-status', storage_type='session'),
    dcc.Interval(id='intervalo-atualizacao', interval=2 * 1000, n_intervals=0),
    get_navbar(),
    html.Div(id='page-content')
])


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


# --- INÍCIO DA CORREÇÃO (Callback Unificado com Variável Global) ---

@app.callback(
    [Output('store-dados-sessao', 'data'),
     Output('store-ultimo-status', 'data')],
    Input('intervalo-atualizacao', 'n_intervals'),
)
def update_data_and_check_alerts(n_intervals):
    """
    Este callback unificado lê o status DIRETAMENTE da variável
    global 'data_source.STATUS_ATUAL_ALERTAS', garantindo que o estado
    lido é 100% síncrono, já que 'use_reloader=False' garante
    um único processo.
    """

    # --- 1. Buscar Novos Dados ---
    print(f"Atualização (Intervalo {n_intervals}): Buscando dados...")
    df_completo = data_source.get_data()
    dados_json_output = df_completo.to_json(date_format='iso', orient='split')

    # --- 2. Verificar Alertas ---

    # Lê o dicionário global do servidor (estado síncrono)
    status_antigos = data_source.STATUS_ATUAL_ALERTAS

    try:
        df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
    except Exception as e:
        print(f"Erro ao converter timestamp em callback unificado: {e}")
        return dados_json_output, dash.no_update

    # Loop para verificar status individual
    for id_ponto, config in data_source.PONTOS_DE_ANALISE.items():

        status_geral_antigo_ponto = status_antigos.get(id_ponto, "INDEFINIDO")
        df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
        status_envio = "SEM DADOS"  # Padrão

        if not df_ponto.empty:
            try:
                df_chuva_72h = processamento.calcular_acumulado_72h(df_ponto)
                ultima_chuva_72h = df_chuva_72h.iloc[-1]['chuva_mm'] if not df_chuva_72h.empty and not pd.isna(
                    df_chuva_72h.iloc[-1]['chuva_mm']) else None
                status_envio, _ = processamento.definir_status_chuva(ultima_chuva_72h)
            except Exception as e_calc:
                print(f"Erro cálculo alerta para {id_ponto}: {e_calc}");
                status_envio = "ERRO"

        # Lógica de Alerta e Transição de Estado por Ponto
        if status_envio != status_geral_antigo_ponto:
            print(f"ALERTA INDIVIDUAL (Chuva): Ponto {id_ponto} mudou de {status_geral_antigo_ponto} -> {status_envio}")
            deve_enviar = False

            # REGRA 1: ALERTA -> PARALIZAÇÃO (Crítico)
            if status_envio == "PARALIZAÇÃO" and status_geral_antigo_ponto == "ALERTA":
                deve_enviar = True
                print(
                    f">>> Transição CRÍTICA {id_ponto} ({status_geral_antigo_ponto}->{status_envio}) detectada. Disparando alarme.")

            # REGRA 2: ATENÇÃO -> LIVRE (Retorno à Normalidade)
            elif status_envio == "LIVRE" and status_geral_antigo_ponto == "ATENÇÃO":
                deve_enviar = True
                print(
                    f">>> Transição de NORMALIZAÇÃO {id_ponto} ({status_geral_antigo_ponto}->{status_envio}) detectada. Disparando alarme.")

            if deve_enviar:
                try:
                    alertas.enviar_alerta(
                        id_ponto,
                        config.get('nome', id_ponto),
                        status_envio,  # Novo Status
                        status_geral_antigo_ponto  # Status Anterior
                    )
                except Exception as e:
                    print(f"AVISO: Falha na notificação para {id_ponto}. Erro: {e}")

            # ATUALIZA O ESTADO GLOBAL IMEDIATAMENTE
            status_antigos[id_ponto] = status_envio
        else:
            pass  # O estado global já está correto

    status_json_output = json.dumps(status_antigos)

    return dados_json_output, status_json_output


# --- FIM DA CORREÇÃO ---


# --- SEÇÃO DE EXECUÇÃO LOCAL ---
if __name__ == '__main__':
    host = '127.0.0.1'
    port = 8050
    print("Inicializando servidor Dash...")
    print(f"Aplicação rodando em: http://{host}:{port}/")
    print("Clique no link acima.")

    # --- ALTERAÇÃO CRÍTICA ---
    # Desativa o 'reloader' para forçar um único processo,
    # o que permite que a variável global de status funcione.
    app.run(debug=True, use_reloader=False, host=host, port=port)
    # --- FIM DA ALTERAÇÃO ---