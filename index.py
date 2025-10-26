# index.py (CORRIGIDO - Definição de nome_do_ponto_gatilho e Lógica de Transição)

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


# --- Layout da Barra de Navegação ---
def get_navbar():
    # ... (código mantido idêntico) ...
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


# --- Layout Principal da Aplicação ---
# (Mantido idêntico)
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


# Callback 2: Atualização de Dados (Background) (Mantido)
@app.callback(Output('store-dados-sessao', 'data'), Input('intervalo-atualizacao', 'n_intervals'))
def carregar_dados_em_background(n_intervals):
    import data_source
    print(f"Atualização background (Intervalo {n_intervals}): Buscando dados...")
    df = data_source.get_data();
    return df.to_json(date_format='iso', orient='split')


# Callback 3: Verificação de Alertas (Background)
@app.callback(Output('store-ultimo-status', 'data'), Input('store-dados-sessao', 'data'),
              State('store-ultimo-status', 'data'))
def verificar_alertas_em_background(dados_json, status_antigo_json):
    if not dados_json: return dash.no_update
    from io import StringIO
    import pandas as pd
    import data_source

    status_antigos = json.loads(status_antigo_json) if status_antigo_json else {}
    status_novos_gerais = {}  # Armazena o status geral (Chuva OU Umidade)

    try:
        df_completo = pd.read_json(StringIO(dados_json), orient='split')
        df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])
    except Exception as e:
        print(f"Erro ao ler JSON em callback de alerta: {e}")
        return dash.no_update

    # Loop para verificar status individual (FORA do try de leitura)
    for id_ponto, config in data_source.PONTOS_DE_ANALISE.items():
        df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
        status_geral_antigo_ponto = status_antigos.get(id_ponto, "INDEFINIDO")
        risco_chuva = -1
        risco_umidade = -1
        status_chuva_txt = "SEM DADOS"
        status_umid_txt = "SEM DADOS"

        constantes_ponto = config.get('constantes', {})
        base_1m = constantes_ponto.get('UMIDADE_BASE_1M', 0.0)
        base_2m = constantes_ponto.get('UMIDADE_BASE_2M', 0.0)
        base_3m = constantes_ponto.get('UMIDADE_BASE_3M', 0.0)

        if not df_ponto.empty:
            try:
                df_chuva_72h = processamento.calcular_acumulado_72h(df_ponto)
                ultima_chuva_72h = None
                if not df_chuva_72h.empty:
                    chuva_val = df_chuva_72h.iloc[-1]['chuva_mm']
                    if not pd.isna(chuva_val): ultima_chuva_72h = chuva_val

                status_chuva_txt, _ = processamento.definir_status_chuva(ultima_chuva_72h)
                risco_chuva = RISCO.get(status_chuva_txt, -1)

                ultimo_dado = df_ponto.iloc[-1]
                umidade_1m_atual = ultimo_dado.get('umidade_1m_perc', None)
                umidade_2m_atual = ultimo_dado.get('umidade_2m_perc', None)
                umidade_3m_atual = ultimo_dado.get('umidade_3m_perc', None)

                status_umid_txt, _, _ = processamento.definir_status_umidade_hierarquico(
                    umidade_1m_atual, umidade_2m_atual, umidade_3m_atual, base_1m, base_2m, base_3m
                )
                risco_umidade = RISCO.get(status_umid_txt, -1)

            except Exception as e_calc:
                print(f"Erro cálculo alerta para {id_ponto}: {e_calc}")
                status_chuva_txt = "ERRO"
                status_umid_txt = "ERRO"
                risco_chuva = -1
                risco_umidade = -1

        risco_geral_novo = max(risco_chuva, risco_umidade)
        if risco_chuva == -1 and risco_umidade == 0: risco_geral_novo = -1
        if risco_umidade == -1 and risco_chuva == 0: risco_geral_novo = -1

        status_geral_novo_txt, status_geral_novo_cor = mapa_status_cor_geral.get(risco_geral_novo,
                                                                                 ("INDEFINIDO", "secondary"))
        if risco_umidade > risco_chuva and risco_umidade > 0:
            status_geral_novo_txt, status_geral_novo_cor, _ = processamento.STATUS_MAP_HIERARQUICO[risco_umidade]

        # Armazena o status geral final (Chuva ou Umidade)
        status_novos_gerais[id_ponto] = status_geral_novo_txt

        # Lógica de alerta individual (REGISTRA APENAS LOG)
        if status_geral_novo_txt != status_geral_antigo_ponto:
            print(
                f"ALERTA INDIVIDUAL: Ponto {id_ponto} mudou de {status_geral_antigo_ponto} -> {status_geral_novo_txt}")

            # Converte nomes do fluxograma para nomes padrão para o log
            status_log = status_geral_novo_txt
            if status_log == "VERMELHO":
                status_log = "PARALIZAÇÃO"
            elif status_log == "LARANJA":
                status_log = "ALERTA"
            elif status_log == "AMARELO":
                status_log = "ATENÇÃO"

            if status_log in ["ATENÇÃO", "ALERTA", "PARALIZAÇÃO"]:
                # Esta linha só registra o log, e-mail/SMS DESATIVADO
                print(
                    f"--- Aviso: Alerta Individual {status_log} detectado para {id_ponto}, mas o envio de e-mail/SMS foi desativado. ---")
            else:
                print(f"Ponto {id_ponto} normalizado. (Status Geral: {status_geral_novo_txt}).")

    # --- INÍCIO DA LÓGICA (ALERTA DE PARALIZAÇÃO TOTAL - CONTROLE DE TRANSIÇÃO) ---

    # 1. Obter o status geral anterior (SISTEMA_GERAL) do store de status antigos
    ultimo_status_geral_enviado = status_antigos.get('SISTEMA_GERAL', 'NAO_PARALISADO')

    # 2. Verificar se TODOS os pontos estão em PARALIZAÇÃO AGORA
    todos_paralizados_agora = False
    if status_novos_gerais and len(status_novos_gerais) == len(data_source.PONTOS_DE_ANALISE):
        todos_paralizados_agora = all(
            status in ["PARALIZAÇÃO", "VERMELHO"] for status in status_novos_gerais.values()
        )

    # 3. Definir o NOVO estado lógico do sistema
    novo_status_geral_logico = 'PARALISADO' if todos_paralizados_agora else 'NAO_PARALISADO'

    # 4. Enviar alerta APENAS se o estado lógico MUDOU (Controle de Transição)

    # Define as variáveis de identificação para a chamada do alerta (para evitar NameError)
    ID_ALERTA_GERAL = "SISTEMA_GERAL"
    NOME_ALERTA_GERAL = "Todos os Pontos"

    # Verifica a transição e TENTA enviar o alerta
    if novo_status_geral_logico != ultimo_status_geral_enviado:

        if novo_status_geral_logico == 'PARALISADO':
            print("ALERTA DE SISTEMA: Todos os pontos entraram em PARALIZAÇÃO TOTAL. DISPARANDO EMAIL/SMS.")
            try:
                # Tenta notificar - APENAS UMA VEZ POR TRANSIÇÃO
                alertas.enviar_alerta(
                    ID_ALERTA_GERAL,
                    NOME_ALERTA_GERAL,
                    "PARALIZAÇÃO TOTAL",
                    "danger"  # Cor 'danger' (vermelho)
                )
            except Exception as e:
                # Captura a exceção de falha total de notificação
                print(f"FALHA NO ENVIO GERAL (PARALIZAÇÃO): {e}")

        elif novo_status_geral_logico == 'NAO_PARALISADO':
            print("ALERTA DE SISTEMA: O sistema SAIU da PARALIZAÇÃO TOTAL. DISPARANDO EMAIL/SMS.")
            try:
                # Tenta notificar - APENAS UMA VEZ POR TRANSIÇÃO
                alertas.enviar_alerta(
                    ID_ALERTA_GERAL,
                    NOME_ALERTA_GERAL,
                    "SISTEMA NORMALIZADO",
                    "success"
                )
            except Exception as e:
                # Captura a exceção de falha total de notificação
                print(f"FALHA NO ENVIO GERAL (NORMALIZAÇÃO): {e}")

        # --- A CORREÇÃO FINAL: SALVAR O ESTADO ---
        # Se houve uma transição, SEMPRE salve o novo estado lógico para bloquear a repetição,
        # independentemente do resultado do try/except acima.
        status_novos_gerais['SISTEMA_GERAL'] = novo_status_geral_logico
        print("AVISO: Transição de estado total registrada e salvada. Repetição bloqueada.")

    else:
        print(f"Alerta Geral: {novo_status_geral_logico}. Sem mudança de estado total, não envia e-mail/SMS.")
        # Se não houve transição, apenas garante que o estado atual seja persistido
        status_novos_gerais['SISTEMA_GERAL'] = novo_status_geral_logico

        # --- FIM DA NOVA LÓGICA ---

    # Salva o dicionário de status individuais (AGORA INCLUINDO O NOVO STATUS GERAL)
    return json.dumps(status_novos_gerais)


# Callback para o toggler do navbar (Ainda comentado)
# @app.callback(...)
# def toggle_navbar_collapse(n, is_open): ...

# --- SEÇÃO DE EXECUÇÃO LOCAL ---
if __name__ == '__main__':
    host = '127.0.0.1'
    port = 8050
    print("Inicializando servidor Dash...")
    print(f"Aplicação rodando em: http://{host}:{port}/")
    print("Clique no link acima.")
    app.run(debug=True, host=host, port=port)