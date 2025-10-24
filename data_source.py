# data_source.py (CORRIGIDO com Suavização Pura e Fatores Assimétricos)

import pandas as pd
import numpy as np
# (Restante dos imports mantidos)
import httpx
import os
import random
import datetime
from math import floor

def _gerar_script_de_chuva_ciclico(total_chuva_mm, horas_chuva, horas_seca, pontos_por_hora, num_eventos_chuva):
    # ... (Função mantida idêntica, com correção de índice) ...
    total_pontos_chuva = horas_chuva * pontos_por_hora
    total_pontos_seca = horas_seca * pontos_por_hora
    script_chuva = np.zeros(total_pontos_chuva)
    eventos_reais = min(num_eventos_chuva, total_pontos_chuva)
    populacao_indices = np.arange(total_pontos_chuva)
    if eventos_reais > len(populacao_indices):
       eventos_reais = len(populacao_indices)

    if eventos_reais > 0:
        indices_de_chuva = np.random.choice(populacao_indices, eventos_reais, replace=False)
        valores_chuva = np.random.rand(eventos_reais)
        if np.sum(valores_chuva) > 0:
            valores_chuva /= np.sum(valores_chuva)
        valores_chuva *= total_chuva_mm
        # Ensure indices are within bounds before assignment
        valid_indices = indices_de_chuva[indices_de_chuva < len(script_chuva)]
        # Ensure values align with valid indices
        valid_valores = valores_chuva[indices_de_chuva < len(script_chuva)]
        if len(valid_indices) > 0:
             script_chuva[valid_indices] = valid_valores


    script_seca = np.zeros(total_pontos_seca)
    script_final = np.concatenate((script_chuva, script_seca))
    print(f"  -> Script de chuva gerado: {len(script_final)} pontos ({horas_chuva}h chuva + {horas_seca}h seca), somando {np.sum(script_final):.1f}mm.")
    return list(script_final)


# --- Constantes para a Chuva (ALINHADAS COM processamento.py) ---
CHUVA_LIMITE_VERDE = 50.0
CHUVA_LIMITE_AMARELO = 69.0
CHUVA_LIMITE_LARANJA = 89.0

# --- Constantes do Simulador (Geral) ---
CONSTANTES_PADRAO = {
    "UMIDADE_BASE_1M": 28.0, "UMIDADE_BASE_2M": 24.0, "UMIDADE_BASE_3M": 22.0,
    "UMIDADE_SATURACAO": 45.0,
    # Fator de Subida (lento)
    "FATOR_SUAVIZACAO_UMIDADE_SUBIDA": 0.05,
    # Fatores de Descida (rápidos e distintos)
    "FATOR_SUAVIZACAO_UMIDADE_DESCIDA_1M": 0.30,
    "FATOR_SUAVIZACAO_UMIDADE_DESCIDA_2M": 0.15,
    "FATOR_SUAVIZACAO_UMIDADE_DESCIDA_3M": 0.05,
    # (Tempos de secagem linear removidos)
    # Constantes de Limites
    "LIMITE_CHUVA_24H": 85.0,
    "LIMITE_CHUVA_72H": 200.0,
}
PERFIL_PONTO_BASE = CONSTANTES_PADRAO.copy();
PERFIL_PONTO_BASE.update({"UMIDADE_BASE_1M": 25.0})

# (Restante das definições globais mantido)
PONTOS_DE_ANALISE = {
    "Ponto-A-KM67": {"nome": "KM 67", "constantes": PERFIL_PONTO_BASE, "lat_lon": [-23.585137, -45.456733]},
    "Ponto-B-KM72": {"nome": "KM 72", "constantes": PERFIL_PONTO_BASE, "lat_lon": [-23.592805, -45.447181]},
    "Ponto-C-KM74": {"nome": "KM 74", "constantes": PERFIL_PONTO_BASE, "lat_lon": [-23.589068, -45.440229]},
    "Ponto-D-KM81": {"nome": "KM 81", "constantes": PERFIL_PONTO_BASE, "lat_lon": [-23.613498, -45.431119]}, }
print("Inicializando dicionários de simuladores...");
SIMULADORES_GLOBAIS = {};
DADOS_HISTORICOS_GLOBAIS = {}
FREQUENCIA_SIMULACAO = datetime.timedelta(minutes=10)
MAX_HISTORY_POINTS = 14 * 24 * 6
PASSOS_POR_ATUALIZACAO = 6


# ==============================================================================
# --- CLASSE SensorSimulator ---
# ==============================================================================
class SensorSimulator:
    def __init__(self, constantes):
        # ... (init mantido idêntico) ...
        self.c = constantes
        self.umidade_1m = self.c['UMIDADE_BASE_1M'];
        self.umidade_2m = self.c['UMIDADE_BASE_2M'];
        self.umidade_3m = self.c['UMIDADE_BASE_3M']
        self.rain_script = []
        self.simulation_cycle_index = 0
        # (ciclos_sem_chuva e umidade_inicio_seca removidos)

    # --- MÉTODO _simular_chuva (Mantido Idêntico) ---
    def _simular_chuva(self, history_data, current_timestamp_utc):
        # ... (código mantido) ...
        total_chuva_72h = 0.0
        limite_72h = (current_timestamp_utc - datetime.timedelta(hours=72)).replace(tzinfo=datetime.timezone.utc)
        for dado in reversed(history_data):
            try:
                if not isinstance(dado, dict): continue
                dado_timestamp_str = dado.get('timestamp')
                if not dado_timestamp_str: continue
                dado_timestamp = datetime.datetime.fromisoformat(dado_timestamp_str.replace('Z', '+00:00'))
                if dado_timestamp < limite_72h: break
                chuva_dado = dado.get('pluviometria_mm', 0.0)
                if dado_timestamp >= limite_72h:
                    total_chuva_72h += chuva_dado
            except Exception:
                continue
        if total_chuva_72h >= self.c['LIMITE_CHUVA_72H']:
            print(f"[{current_timestamp_utc.strftime('%Y-%m-%d %H:%M')}] ALERTA DE SEGURANÇA: Limite 72h ({self.c['LIMITE_CHUVA_72H']}mm) atingido ({total_chuva_72h:.1f}mm).")
            return 0.0
        if not hasattr(self, 'rain_script') or len(self.rain_script) == 0:
            print("ERRO: Simulador não inicializado com script de chuva.")
            return 0.0
        script_index = self.simulation_cycle_index % len(self.rain_script)
        chuva_mm = self.rain_script[script_index]
        return round(chuva_mm, 2)

    # --- MÉTODO _simular_umidade (REESCRITO COM FATORES ASSIMÉTRICOS) ---
    def _simular_umidade(self, history_data, current_timestamp_utc, chuva_mm_neste_passo):

        # 1. Calcular o acumulado 72h atual (igual)
        # ... (código mantido) ...
        total_chuva_72h = 0.0
        limite_72h = (current_timestamp_utc - datetime.timedelta(hours=72)).replace(tzinfo=datetime.timezone.utc)
        for dado in reversed(history_data): # history_data já inclui a chuva deste passo
            try:
                if not isinstance(dado, dict): continue
                dado_timestamp_str = dado.get('timestamp')
                if not dado_timestamp_str: continue
                dado_timestamp = datetime.datetime.fromisoformat(dado_timestamp_str.replace('Z', '+00:00'))
                if dado_timestamp < limite_72h: break
                chuva_dado = dado.get('pluviometria_mm', 0.0)
                if dado_timestamp >= limite_72h:
                    total_chuva_72h += chuva_dado
            except Exception:
                continue
        total_chuva_72h = round(total_chuva_72h, 2)


        # 2. Calcular a "Umidade Alvo" baseada na chuva (igual)
        # ... (código mantido) ...
        base_1m = self.c['UMIDADE_BASE_1M']
        base_2m = self.c['UMIDADE_BASE_2M']
        base_3m = self.c['UMIDADE_BASE_3M']
        saturacao = self.c['UMIDADE_SATURACAO']
        target_1m = np.interp(total_chuva_72h, [0, CHUVA_LIMITE_VERDE], [base_1m, saturacao])
        target_2m = np.interp(total_chuva_72h, [CHUVA_LIMITE_VERDE, CHUVA_LIMITE_AMARELO], [base_2m, saturacao])
        target_3m = np.interp(total_chuva_72h, [CHUVA_LIMITE_AMARELO, CHUVA_LIMITE_LARANJA], [base_3m, saturacao])
        # Clamp dos Alvos
        if total_chuva_72h < CHUVA_LIMITE_VERDE:
            target_2m = base_2m
            target_3m = base_3m
        elif total_chuva_72h < CHUVA_LIMITE_AMARELO:
            target_3m = base_3m
        target_1m = min(target_1m, saturacao); target_1m = max(target_1m, base_1m)
        target_2m = min(target_2m, saturacao); target_2m = max(target_2m, base_2m)
        target_3m = min(target_3m, saturacao); target_3m = max(target_3m, base_3m)

        # 3. APLICAR SUAVIZAÇÃO (COM FATORES DIFERENTES PARA SUBIDA/DESCIDA)
        fator_subida = self.c.get("FATOR_SUAVIZACAO_UMIDADE_SUBIDA", 0.05)
        fator_descida_1m = self.c.get("FATOR_SUAVIZACAO_UMIDADE_DESCIDA_1M", 0.30)
        fator_descida_2m = self.c.get("FATOR_SUAVIZACAO_UMIDADE_DESCIDA_2M", 0.15)
        fator_descida_3m = self.c.get("FATOR_SUAVIZACAO_UMIDADE_DESCIDA_3M", 0.05)

        # Sensor 1m
        delta_1m = target_1m - self.umidade_1m
        fator_1m = fator_subida if delta_1m > 0 else fator_descida_1m
        self.umidade_1m += delta_1m * fator_1m

        # Sensor 2m
        delta_2m = target_2m - self.umidade_2m
        fator_2m = fator_subida if delta_2m > 0 else fator_descida_2m
        self.umidade_2m += delta_2m * fator_2m

        # Sensor 3m
        delta_3m = target_3m - self.umidade_3m
        fator_3m = fator_subida if delta_3m > 0 else fator_descida_3m
        self.umidade_3m += delta_3m * fator_3m

        # 4. Garantir Limites Finais (Clamp) - Mantido
        self.umidade_1m = min(self.umidade_1m, saturacao); self.umidade_1m = max(self.umidade_1m, base_1m)
        self.umidade_2m = min(self.umidade_2m, saturacao); self.umidade_2m = max(self.umidade_2m, base_2m)
        self.umidade_3m = min(self.umidade_3m, saturacao); self.umidade_3m = max(self.umidade_3m, base_3m)


    def gerar_novo_dado(self, timestamp_utc, history_data):
        # (Esta função permanece idêntica)
        # ... (código mantido) ...
        chuva_mm_neste_passo = self._simular_chuva(history_data, timestamp_utc);
        self.simulation_cycle_index += 1
        ts_str = timestamp_utc.isoformat().replace('+00:00', 'Z')
        novo_dado_chuva = {"timestamp": ts_str, "pluviometria_mm": round(chuva_mm_neste_passo, 2)}
        history_data_com_chuva = history_data + [novo_dado_chuva]
        self._simular_umidade(history_data_com_chuva, timestamp_utc, chuva_mm_neste_passo)
        novo_acumulado = 0.0
        if history_data:
            try:
                # Calcula acumulado com base no histórico ANTES deste passo
                prev_accum = history_data[-1].get('precipitacao_acumulada_mm', 0.0)
                novo_acumulado = prev_accum + chuva_mm_neste_passo
            except (IndexError, AttributeError, KeyError):
                 novo_acumulado = chuva_mm_neste_passo # Se não houver histórico, começa do zero
        else:
             novo_acumulado = chuva_mm_neste_passo
        return {"timestamp": ts_str, "pluviometria_mm": round(chuva_mm_neste_passo, 2),
                "precipitacao_acumulada_mm": round(novo_acumulado, 2),
                "umidade_1m_perc": round(self.umidade_1m, 2), "umidade_2m_perc": round(self.umidade_2m, 2),
                "umidade_3m_perc": round(self.umidade_3m, 2)}
# ============================================================================
# --- FIM: CLASSE SensorSimulator ---
# ============================================================================


# ============================================================================
# --- GERENCIAMENTO DE MÚLTIPLOS PONTOS ---
# ============================================================================
def _inicializar_simuladores():
    # (Esta função permanece idêntica)
    # ... (código mantido) ...
    global DADOS_HISTORICOS_GLOBAIS, SIMULADORES_GLOBAIS
    if SIMULADORES_GLOBAIS: return
    print("Inicializando simuladores ('real-time')...")
    agora_utc = datetime.datetime.now(datetime.timezone.utc)
    minutos_truncados = floor(agora_utc.minute / 10) * 10
    timestamp_inicial = agora_utc.replace(minute=minutos_truncados, second=0, microsecond=0)
    PONTOS_POR_HORA = int(60 / (FREQUENCIA_SIMULACAO.total_seconds() / 60))
    for id_ponto, config in PONTOS_DE_ANALISE.items():
        print(f"  - Inicializando {id_ponto} ({config['nome']})...")
        simulador = SensorSimulator(config['constantes'])
        simulador.rain_script = _gerar_script_de_chuva_ciclico(
            total_chuva_mm=120.0, horas_chuva=72, horas_seca=72,
            pontos_por_hora=PONTOS_POR_HORA, num_eventos_chuva=100
        )
        simulador.simulation_cycle_index = 0
        SIMULADORES_GLOBAIS[id_ponto] = simulador
        primeiro_dado = simulador.gerar_novo_dado(timestamp_inicial, []) # Passa lista vazia
        DADOS_HISTORICOS_GLOBAIS[id_ponto] = [primeiro_dado]
    print("Simuladores inicializados com scripts de chuva cíclicos (72h chuva + 72h seca).")


def get_dados_reais_zentra(): print("CHAMANDO API..."); raise NotImplementedError("API não conectada")


def get_dados_simulados():
    # (Esta função permanece idêntica)
    # ... (código mantido) ...
    global DADOS_HISTORICOS_GLOBAIS, SIMULADORES_GLOBAIS
    if not SIMULADORES_GLOBAIS: _inicializar_simuladores()
    dfs_de_todos_os_pontos = [];
    total_novos_pontos_gerados = 0
    for id_ponto, simulador in SIMULADORES_GLOBAIS.items():
        historico_ponto = DADOS_HISTORICOS_GLOBAIS[id_ponto]
        if not historico_ponto:
            # ... (código de reinicialização mantido) ...
            print(f"AVISO: Histórico vazio para {id_ponto}, tentando reinicializar...");
            _inicializar_simuladores();
            historico_ponto = DADOS_HISTORICOS_GLOBAIS[id_ponto]
            if not historico_ponto: print(f"ERRO: Falha ao reinicializar {id_ponto}"); continue
        # (Lógica de aceleração mantida)
        novos_dados_nesta_rodada = [] # Acumula os 6 novos dados aqui
        historico_atualizado = list(historico_ponto) # Copia para passar para gerar_novo_dado
        for i in range(PASSOS_POR_ATUALIZACAO):
            try:
                ultimo_timestamp_str = historico_atualizado[-1]['timestamp']
            except (IndexError, KeyError, ValueError) as e:
                 print(f"ERRO no passo {i+1}: Falha ao ler último timestamp do {id_ponto}: {e}. Pulando o resto.");
                 break # Pula o resto dos passos para este ponto
            ultimo_timestamp = datetime.datetime.fromisoformat(ultimo_timestamp_str.replace('Z', '+00:00'))
            proximo_timestamp = ultimo_timestamp + FREQUENCIA_SIMULACAO
            # Passa o histórico que inclui os dados gerados NESTA rodada
            novo_dado = simulador.gerar_novo_dado(proximo_timestamp, historico_atualizado)
            novos_dados_nesta_rodada.append(novo_dado)
            historico_atualizado.append(novo_dado) # Atualiza o histórico para o próximo passo
            total_novos_pontos_gerados += 1

        # Atualiza o histórico global DEPOIS de gerar todos os 6 passos
        DADOS_HISTORICOS_GLOBAIS[id_ponto].extend(novos_dados_nesta_rodada)
        DADOS_HISTORICOS_GLOBAIS[id_ponto] = DADOS_HISTORICOS_GLOBAIS[id_ponto][-MAX_HISTORY_POINTS:]

        #print( f"  - {id_ponto}: {len(novos_dados_nesta_rodada)}/{PASSOS_POR_ATUALIZACAO} novos pontos simulados. Hist: {len(DADOS_HISTORICOS_GLOBAIS[id_ponto])} pts.")

        df_ponto = pd.DataFrame(DADOS_HISTORICOS_GLOBAIS[id_ponto]);
        df_ponto['id_ponto'] = id_ponto;
        dfs_de_todos_os_pontos.append(df_ponto)
    # ... (código de retorno do DataFrame mantido) ...
    if not dfs_de_todos_os_pontos:
        # ... (código mantido) ...
        print("AVISO: Nenhum DataFrame gerado.");
        colunas_finais = ['id_ponto', 'timestamp', 'chuva_mm', 'precipitacao_acumulada_mm', 'umidade_1m_perc',
                          'umidade_2m_perc', 'umidade_3m_perc'];
        return pd.DataFrame(columns=colunas_finais)
    df_final = pd.concat(dfs_de_todos_os_pontos, ignore_index=True);
    df_final['timestamp'] = pd.to_datetime(df_final['timestamp']);
    df_final = df_final.rename(columns={'pluviometria_mm': 'chuva_mm'})
    colunas_finais = ['id_ponto', 'timestamp', 'chuva_mm', 'precipitacao_acumulada_mm', 'umidade_1m_perc',
                      'umidade_2m_perc', 'umidade_3m_perc'];
    df_final = df_final[[col for col in colunas_finais if col in df_final.columns]];
    return df_final


def get_data():
    # (Esta função permanece idêntica)
    # ... (código mantido) ...
    USA_API_REAL = False
    if USA_API_REAL:
        try:
            return get_dados_reais_zentra()
        except Exception as e:
            print(f"CRÍTICO: Falha API: {e}"); return get_dados_simulados()
    else:
        return get_dados_simulados()