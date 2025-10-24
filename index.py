import dash
from dash import dcc, html, Input, Output, State
import pandas as pd
import json
from io import StringIO
import datetime  # Para o mapa de risco

# Importa o app central (que inicializa o Dash)
from app import app, server

# Importa as "páginas"
from pages import map_view, specific_dash, general_dash

# Importa os módulos de backend
import data_source
import processamento  # Agora tem definir_status_chuva e definir_status_umidade_hierarquico
import alertas

# --- Constantes para Alerta Geral (Mapa de Risco) ---
RISCO = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3, "SEM DADOS": -1, "INDEFINIDO": -1}
mapa_status_cor_geral = {0: ("LIVRE", "success"), 1: ("ATENÇÃO", "warning"), 2: ("ALERTA", "orange"),
                         3: ("PARALIZAÇÃO", "danger"), -1: ("SEM DADOS", "secondary")}
# ----------------------------------------------------

# --- Layout Principal (O "Roteador") ---
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='store-dados-sessao', storage_type='session'),
    dcc.Store(id='store-ultimo-status', storage_type='session'),
    dcc.Interval(id='intervalo-atualizacao', interval=2 * 1000, n_intervals=0),  # 2 segundos
    html.Div(id='page-content')
])


# --- Callback 1: O Roteador de Páginas ---
@app.callback(Output('page-content', 'children'), Input('url', 'pathname'))
def display_page(pathname):
    if pathname.startswith('/ponto/'):
        return specific_dash.get_layout()
    elif pathname == '/dashboard-geral':
        return general_dash.get_layout()
    else:
        return map_view.get_layout()


# --- Callback 2: Atualização de Dados (Background) ---
@app.callback(Output('store-dados-sessao', 'data'), Input('intervalo-atualizacao', 'n_intervals'))
def carregar_dados_em_background(n_intervals):
    print(f"Atualização background (Intervalo {n_intervals}): Buscando dados...")
    df = data_source.get_data();
    return df.to_json(date_format='iso', orient='split')


# --- Callback 3: Verificação de Alertas (Background) - CORRIGIDO ---
@app.callback(Output('store-ultimo-status', 'data'), Input('store-dados-sessao', 'data'),
              State('store-ultimo-status', 'data'))
def verificar_alertas_em_background(dados_json, status_antigo_json):
    if not dados_json: return dash.no_update

    status_antigos = json.loads(status_antigo_json) if status_antigo_json else {}
    status_novos_gerais = {}

    df_completo = pd.read_json(StringIO(dados_json), orient='split');
    df_completo['timestamp'] = pd.to_datetime(df_completo['timestamp'])

    print("Verificando alertas em background...")

    for id_ponto, config in data_source.PONTOS_DE_ANALISE.items():
        df_ponto = df_completo[df_completo['id_ponto'] == id_ponto]
        status_geral_antigo_ponto = status_antigos.get(id_ponto, "INDEFINIDO")

        risco_chuva = -1;
        risco_umidade = -1
        status_chuva_txt = "SEM DADOS";
        status_umid_txt = "SEM DADOS"

        if not df_ponto.empty:
            # 1. Status da Chuva
            df_chuva_72h = processamento.calcular_acumulado_72h(df_ponto)
            ultima_chuva_72h = df_chuva_72h.iloc[-1]['chuva_mm'] if not df_chuva_72h.empty else None
            status_chuva_txt, status_chuva_col = processamento.definir_status_chuva(ultima_chuva_72h)
            risco_chuva = RISCO.get(status_chuva_txt, -1)

            # 2. Status da Umidade (Hierárquico)
            ultimo_dado = df_ponto.iloc[-1]
            umidade_1m_atual = ultimo_dado.get('umidade_1m_perc', None)
            umidade_2m_atual = ultimo_dado.get('umidade_2m_perc', None)
            umidade_3m_atual = ultimo_dado.get('umidade_3m_perc', None)

            base_1m = config['constantes'].get('UMIDADE_BASE_1M', 0.0)
            base_2m = config['constantes'].get('UMIDADE_BASE_2M', 0.0)
            base_3m = config['constantes'].get('UMIDADE_BASE_3M', 0.0)

            # --- CORREÇÃO: Chama a nova função hierárquica ---
            status_umid_txt, status_umid_col, _ = processamento.definir_status_umidade_hierarquico(
                umidade_1m_atual, umidade_2m_atual, umidade_3m_atual, base_1m, base_2m, base_3m
            )
            risco_umidade = RISCO.get(status_umid_txt, -1)

        # 3. Determina o status GERAL MAIS CRÍTICO
        risco_geral_novo = max(risco_chuva, risco_umidade)
        status_geral_novo_txt, status_geral_novo_cor = mapa_status_cor_geral.get(risco_geral_novo,
                                                                                 ("INDEFINIDO", "secondary"))

        # 4. Envia Alerta se houver mudança
        status_novos_gerais[id_ponto] = status_geral_novo_txt

        if status_geral_novo_txt != status_geral_antigo_ponto:
            print(f"ALERTA GERAL: Ponto {id_ponto} mudou de {status_geral_antigo_ponto} -> {status_geral_novo_txt}")

            if status_geral_novo_txt in ["ATENÇÃO", "ALERTA", "PARALIZAÇÃO"]:
                try:
                    alertas.enviar_alerta(id_ponto, config['nome'], status_geral_novo_txt, status_geral_novo_cor)
                except Exception as e:
                    if 'COMTELE_API_KEY' in str(e):
                        print(f"FALHA ALERTA {id_ponto}: Chave COMTELE_API_KEY não definida.")
                    else:
                        print(f"FALHA ALERTA {id_ponto}: {e}")
            else:
                print(f"Ponto {id_ponto} normalizado (Status Geral: {status_geral_novo_txt}).")

    return json.dumps(status_novos_gerais)


# --- Para rodar localmente ---
if __name__ == '__main__':
    host = '127.0.0.1';
    port = 8050
    print("Inicializando servidor Dash...");
    print(f"Aplicação rodando em: http://{host}:{port}/");
    print("Clique no link acima.")
    app.run(debug=True, host=host, port=port)