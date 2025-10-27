# data_source.py (VERSÃO FINAL - Com Estado Síncrono Global)

import pandas as pd
import numpy as np
import httpx
import os
import random
import datetime
from math import floor


# (Mantido da sua versão)
def _gerar_script_de_chuva_ciclico(total_chuva_mm, horas_chuva, horas_seca, pontos_por_hora, num_eventos_chuva):
    # ... (Função mantida idêntica) ...
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
        valid_indices = indices_de_chuva[indices_de_chuva < len(script_chuva)]
        valid_valores = valores_chuva[indices_de_chuva < len(script_chuva)]
        if len(valid_indices) > 0:
            script_chuva[valid_indices] = valid_valores
    script_seca = np.zeros(total_pontos_seca)
    script_final = np.concatenate((script_chuva, script_seca))
    print(
        f"  -> Script de chuva gerado: {len(script_final)} pontos ({horas_chuva}h chuva + {horas_seca}h seca), somando {np.sum(script_final):.1f}mm.")
    return list(script_final)


# --- Constantes de Atraso (Delay) (Mantidas) ---
RISE_S1_START = 0.0;
RISE_S1_END = 55.0
RISE_S2_START = RISE_S1_END;
RISE_S2_END = 72.0  # (Inicia em 55mm)
RISE_S3_START = RISE_S2_END;
RISE_S3_END = 95.0  # (Inicia em 72mm)

FALL_START_ALL = 120.0
FALL_END_1M = 95.0
FALL_END_2M = 69.0
FALL_END_3M = 0.0

# --- Constantes do Simulador (Geral) ---
CONSTANTES_PADRAO = {
    "UMIDADE_BASE_1M": 30.0, "UMIDADE_BASE_2M": 36.0, "UMIDADE_BASE_3M": 39.0,
    "UMIDADE_SATURACAO_1M": 47.0,
    "UMIDADE_SATURACAO_2M": 46.0,
    "UMIDADE_SATURACAO_3M": 49.0,
    "LIMITE_CHUVA_24H": 85.0,
    "LIMITE_CHUVA_72H": 200.0,
}

PERFIL_PONTO_BASE = CONSTANTES_PADRAO.copy();
GATILHO_CHUVA_BASE_MM = 5.0
PONTOS_DE_ANALISE = {
    "Ponto-A-KM67": {"nome": "KM 67", "constantes": PERFIL_PONTO_BASE.copy(), "lat_lon": [-23.585137, -45.456733]},
    "Ponto-B-KM72": {"nome": "KM 72", "constantes": PERFIL_PONTO_BASE.copy(), "lat_lon": [-23.592805, -45.447181]},
    "Ponto-C-KM74": {"nome": "KM 74", "constantes": PERFIL_PONTO_BASE.copy(), "lat_lon": [-23.589068, -45.440229]},
    "Ponto-D-KM81": {"nome": "KM 81", "constantes": PERFIL_PONTO_BASE.copy(), "lat_lon": [-23.613498, -45.431119]}, }
print("Inicializando dicionários de simuladores...");
SIMULADORES_GLOBAIS = {};
DADOS_HISTORICOS_GLOBAIS = {}

# --- ARMAZENAMENTO DE ESTADO SÍNCRONO (EM MEMÓRIA) ---
STATUS_ATUAL_ALERTAS = {}

FREQUENCIA_SIMULACAO = datetime.timedelta(minutes=10)
MAX_HISTORY_POINTS = 14 * 24 * 6
PASSOS_POR_ATUALIZACAO = 6


# ==============================================================================
# --- CLASSE SensorSimulator ---
# ==============================================================================
class SensorSimulator:
    # ... (A classe permanece idêntica à versão anterior) ...
    def __init__(self, constantes):
        self.c = constantes
        self.umidade_1m = 0.0
        self.umidade_2m = 0.0
        self.umidade_3m = 0.0
        self.base_1m_dinamica = self.c.get('UMIDADE_BASE_1M', CONSTANTES_PADRAO['UMIDADE_BASE_1M'])
        self.base_2m_dinamica = self.c.get('UMIDADE_BASE_2M', CONSTANTES_PADRAO['UMIDADE_BASE_2M'])
        self.base_3m_dinamica = self.c.get('UMIDADE_BASE_3M', CONSTANTES_PADRAO['UMIDADE_BASE_3M'])
        self.base_1m_definida = False
        self.base_2m_definida = False
        self.base_3m_definida = False
        self.rain_script = []
        self.simulation_cycle_index = 0
        self.fase_chuva = 'subindo'
        self.pico_chuva_ciclo = 0.0

    def _simular_chuva(self, history_data, current_timestamp_utc):
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
        limite_chuva_72h_config = self.c.get('LIMITE_CHUVA_72H', CONSTANTES_PADRAO.get('LIMITE_CHUVA_72H', 200.0))
        if total_chuva_72h >= limite_chuva_72h_config:
            print(
                f"[{current_timestamp_utc.strftime('%Y-%m-%d %H:%M')}] ALERTA DE SEGURANÇA: Limite 72h ({limite_chuva_72h_config}mm) atingido ({total_chuva_72h:.1f}mm).")
            self.pico_chuva_ciclo = 0.0
            self.fase_chuva = 'subindo'
            return 0.0
        if not hasattr(self, 'rain_script') or len(self.rain_script) == 0:
            print("ERRO: Simulador não inicializado com script de chuva.")
            return 0.0
        script_index = self.simulation_cycle_index % len(self.rain_script)
        chuva_mm = self.rain_script[script_index]
        return round(chuva_mm, 2)

    def _simular_umidade(self, history_data, current_timestamp_utc, chuva_mm_neste_passo):
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
        total_chuva_72h = round(total_chuva_72h, 2)
        total_chuva_72h = max(0.0, min(total_chuva_72h, FALL_START_ALL))
        base_1m = self.c.get('UMIDADE_BASE_1M', CONSTANTES_PADRAO['UMIDADE_BASE_1M'])
        base_2m = self.c.get('UMIDADE_BASE_2M', CONSTANTES_PADRAO['UMIDADE_BASE_2M'])
        base_3m = self.c.get('UMIDADE_BASE_3M', CONSTANTES_PADRAO['UMIDADE_BASE_3M'])
        saturacao_1m = self.c.get('UMIDADE_SATURACAO_1M', CONSTANTES_PADRAO['UMIDADE_SATURACAO_1M'])
        saturacao_2m = self.c.get('UMIDADE_SATURACAO_2M', CONSTANTES_PADRAO['UMIDADE_SATURACAO_2M'])
        saturacao_3m = self.c.get('UMIDADE_SATURACAO_3M', CONSTANTES_PADRAO['UMIDADE_SATURACAO_3M'])
        umidade_1m_calc = self.umidade_1m
        umidade_2m_calc = self.umidade_2m
        umidade_3m_calc = self.umidade_3m
        if self.base_1m_definida:
            if total_chuva_72h > self.pico_chuva_ciclo - 0.1:
                self.fase_chuva = 'subindo'
                self.pico_chuva_ciclo = max(self.pico_chuva_ciclo, total_chuva_72h)
            elif total_chuva_72h < self.pico_chuva_ciclo - 0.5:
                self.fase_chuva = 'descendo'
            if total_chuva_72h < GATILHO_CHUVA_BASE_MM:
                self.pico_chuva_ciclo = total_chuva_72h
                self.fase_chuva = 'subindo'
            if self.fase_chuva == 'subindo':
                if total_chuva_72h <= RISE_S1_END:
                    umidade_1m_calc = np.interp(total_chuva_72h, [RISE_S1_START, RISE_S1_END], [base_1m, saturacao_1m])
                else:
                    umidade_1m_calc = saturacao_1m
                if total_chuva_72h < RISE_S2_START:
                    umidade_2m_calc = base_2m
                elif total_chuva_72h <= RISE_S2_END:
                    umidade_2m_calc = np.interp(total_chuva_72h, [RISE_S2_START, RISE_S2_END], [base_2m, saturacao_2m])
                else:
                    umidade_2m_calc = saturacao_2m
                if total_chuva_72h < RISE_S3_START:
                    umidade_3m_calc = base_3m
                elif total_chuva_72h <= RISE_S3_END:
                    umidade_3m_calc = np.interp(total_chuva_72h, [RISE_S3_START, RISE_S3_END], [base_3m, saturacao_3m])
                else:
                    umidade_3m_calc = saturacao_3m
            else:
                if total_chuva_72h >= FALL_END_1M:
                    umidade_1m_calc = np.interp(total_chuva_72h, [FALL_END_1M, FALL_START_ALL], [base_1m, saturacao_1m])
                else:
                    umidade_1m_calc = base_1m
                if total_chuva_72h >= FALL_END_2M:
                    umidade_2m_calc = np.interp(total_chuva_72h, [FALL_END_2M, FALL_START_ALL], [base_2m, saturacao_2m])
                else:
                    umidade_2m_calc = base_2m
                if total_chuva_72h >= FALL_END_3M:
                    umidade_3m_calc = np.interp(total_chuva_72h, [FALL_END_3M, FALL_START_ALL], [base_3m, saturacao_3m])
                else:
                    umidade_3m_calc = base_3m
        else:
            if total_chuva_72h == 0.0:
                umidade_1m_calc = 0.0
                umidade_2m_calc = 0.0
                umidade_3m_calc = 0.0
                self.pico_chuva_ciclo = 0.0
                self.fase_chuva = 'subindo'
            elif total_chuva_72h < GATILHO_CHUVA_BASE_MM:
                umidade_1m_calc = base_1m + random.uniform(-0.3, 0.3)
                umidade_2m_calc = base_2m + random.uniform(-0.3, 0.3)
                umidade_3m_calc = base_3m + random.uniform(-0.3, 0.3)
                self.pico_chuva_ciclo = total_chuva_72h
                self.fase_chuva = 'subindo'
            else:
                self.base_1m_dinamica = self.umidade_1m
                self.base_1m_definida = True
                print(
                    f"[{current_timestamp_utc.strftime('%H:%M')}] ALERTA BASE 1m (Gatilho {GATILHO_CHUVA_BASE_MM}mm): Nova base definida em {self.base_1m_dinamica:.1f}% (Chuva: {total_chuva_72h:.1f}mm)")
                self.base_2m_dinamica = self.umidade_2m
                self.base_2m_definida = True
                print(
                    f"[{current_timestamp_utc.strftime('%H:%M')}] ALERTA BASE 2m (Gatilho {GATILHO_CHUVA_BASE_MM}mm): Nova base definida em {self.base_2m_dinamica:.1f}% (Chuva: {total_chuva_72h:.1f}mm)")
                self.base_3m_dinamica = self.umidade_3m
                self.base_3m_definida = True
                print(
                    f"[{current_timestamp_utc.strftime('%H:%M')}] ALERTA BASE 3m (Gatilho {GATILHO_CHUVA_BASE_MM}mm): Nova base definida em {self.base_3m_dinamica:.1f}% (Chuva: {total_chuva_72h:.1f}mm)")
                self.fase_chuva = 'subindo'
                self.pico_chuva_ciclo = max(self.pico_chuva_ciclo, total_chuva_72h)
                if total_chuva_72h <= RISE_S1_END:
                    umidade_1m_calc = np.interp(total_chuva_72h, [RISE_S1_START, RISE_S1_END], [base_1m, saturacao_1m])
                else:
                    umidade_1m_calc = saturacao_1m
                if total_chuva_72h < RISE_S2_START:
                    umidade_2m_calc = base_2m
                elif total_chuva_72h <= RISE_S2_END:
                    umidade_2m_calc = np.interp(total_chuva_72h, [RISE_S2_START, RISE_S2_END], [base_2m, saturacao_2m])
                else:
                    umidade_2m_calc = saturacao_2m
                if total_chuva_72h < RISE_S3_START:
                    umidade_3m_calc = base_3m
                elif total_chuva_72h <= RISE_S3_END:
                    umidade_3m_calc = np.interp(total_chuva_72h, [RISE_S3_START, RISE_S3_END], [base_3m, saturacao_3m])
                else:
                    umidade_3m_calc = saturacao_3m
        safe_threshold = 1.0
        if self.base_1m_definida and (umidade_1m_calc < self.base_1m_dinamica) and (umidade_1m_calc > safe_threshold):
            print(
                f"[{current_timestamp_utc.strftime('%H:%M')}] ALERTA BASE 1m: Valor ({umidade_1m_calc:.1f}%) baixou da base ({self.base_1m_dinamica:.1f}%). Nova base definida.")
            self.base_1m_dinamica = umidade_1m_calc
        if self.base_2m_definida and (umidade_2m_calc < self.base_2m_dinamica) and (umidade_2m_calc > safe_threshold):
            print(
                f"[{current_timestamp_utc.strftime('%H:%M')}] ALERTA BASE 2m: Valor ({umidade_2m_calc:.1f}%) baixou da base ({self.base_2m_dinamica:.1f}%). Nova base definida.")
            self.base_2m_dinamica = umidade_2m_calc
        if self.base_3m_definida and (umidade_3m_calc < self.base_3m_dinamica) and (umidade_3m_calc > safe_threshold):
            print(
                f"[{current_timestamp_utc.strftime('%H:%M')}] ALERTA BASE 3m: Valor ({umidade_3m_calc:.1f}%) baixou da base ({self.base_3m_dinamica:.1f}%). Nova base definida.")
            self.base_3m_dinamica = umidade_3m_calc
        if self.base_1m_definida:
            self.umidade_1m = max(self.base_1m_dinamica, min(umidade_1m_calc, saturacao_1m))
        else:
            self.umidade_1m = max(0.0, min(umidade_1m_calc, saturacao_1m))
        if self.base_2m_definida:
            self.umidade_2m = max(self.base_2m_dinamica, min(umidade_2m_calc, saturacao_2m))
        else:
            self.umidade_2m = max(0.0, min(umidade_2m_calc, saturacao_2m))
        if self.base_3m_definida:
            self.umidade_3m = max(self.base_3m_dinamica, min(umidade_3m_calc, saturacao_3m))
        else:
            self.umidade_3m = max(0.0, min(umidade_3m_calc, saturacao_3m))

    def gerar_novo_dado(self, timestamp_utc, history_data):
        chuva_mm_neste_passo = self._simular_chuva(history_data, timestamp_utc);
        self.simulation_cycle_index += 1
        ts_str = timestamp_utc.isoformat().replace('+00:00', 'Z')
        novo_dado_chuva = {"timestamp": ts_str, "pluviometria_mm": round(chuva_mm_neste_passo, 2)}
        history_data_para_umidade = history_data + [novo_dado_chuva]
        self._simular_umidade(history_data_para_umidade, timestamp_utc, chuva_mm_neste_passo)
        novo_acumulado = 0.0
        if history_data:
            try:
                prev_accum = history_data[-1].get('precipitacao_acumulada_mm', 0.0)
                novo_acumulado = prev_accum + chuva_mm_neste_passo
            except (IndexError, AttributeError, KeyError):
                novo_acumulado = chuva_mm_neste_passo
        else:
            novo_acumulado = chuva_mm_neste_passo
        return {"timestamp": ts_str, "pluviometria_mm": round(chuva_mm_neste_passo, 2),
                "precipitacao_acumulada_mm": round(novo_acumulado, 2),
                "umidade_1m_perc": round(self.umidade_1m, 2), "umidade_2m_perc": round(self.umidade_2m, 2),
                "umidade_3m_perc": round(self.umidade_3m, 2),
                "base_1m": round(self.base_1m_dinamica, 2),
                "base_2m": round(self.base_2m_dinamica, 2),
                "base_3m": round(self.base_3m_dinamica, 2)}


# ============================================================================
# --- GERENCIAMENTO DE MÚLTIPLOS PONTOS ---
# ============================================================================
def _inicializar_simuladores():
    # --- Modificado para incluir a variável de estado global ---
    global DADOS_HISTORICOS_GLOBAIS, SIMULADORES_GLOBAIS, STATUS_ATUAL_ALERTAS

    SIMULADORES_GLOBAIS.clear()
    DADOS_HISTORICOS_GLOBAIS.clear()
    # --- Limpa o estado ao reiniciar ---
    STATUS_ATUAL_ALERTAS.clear()

    print("Inicializando simuladores ('real-time')...")
    agora_utc = datetime.datetime.now(datetime.timezone.utc)
    minutos_truncados = floor(agora_utc.minute / 10) * 10
    timestamp_inicial = agora_utc.replace(minute=minutos_truncados, second=0, microsecond=0)
    PONTOS_POR_HORA = int(60 / (FREQUENCIA_SIMULACAO.total_seconds() / 60))
    for id_ponto, config in PONTOS_DE_ANALISE.items():
        print(f"  - Inicializando {id_ponto} ({config['nome']})...")
        simulador = SensorSimulator(config.get('constantes', CONSTANTES_PADRAO.copy()))
        simulador.rain_script = _gerar_script_de_chuva_ciclico(
            total_chuva_mm=120.0, horas_chuva=72, horas_seca=72,
            pontos_por_hora=PONTOS_POR_HORA, num_eventos_chuva=100
        )
        simulador.simulation_cycle_index = 0
        SIMULADORES_GLOBAIS[id_ponto] = simulador
        primeiro_dado = simulador.gerar_novo_dado(timestamp_inicial, [])
        DADOS_HISTORICOS_GLOBAIS[id_ponto] = [primeiro_dado]

        # --- Inicializa o estado de alerta ---
        STATUS_ATUAL_ALERTAS[id_ponto] = "INDEFINIDO"

    print("Simuladores inicializados com scripts de chuva cíclicos (72h chuva + 72h seca).")


def get_dados_reais_zentra(): print("CHAMANDO API..."); raise NotImplementedError("API não conectada")


def get_dados_simulados():
    global DADOS_HISTORICOS_GLOBAIS, SIMULADORES_GLOBAIS
    if not SIMULADORES_GLOBAIS:
        _inicializar_simuladores()
    dfs_de_todos_os_pontos = [];
    total_novos_pontos_gerados = 0
    ids_simuladores = list(SIMULADORES_GLOBAIS.keys())
    for id_ponto in ids_simuladores:
        simulador = SIMULADORES_GLOBAIS.get(id_ponto)
        if not simulador:
            continue
        historico_ponto = DADOS_HISTORICOS_GLOBAIS.get(id_ponto)
        if not historico_ponto:
            print(f"AVISO: Histórico vazio para {id_ponto}, tentando reinicializar...");
            _inicializar_simuladores();
            historico_ponto = DADOS_HISTORICOS_GLOBAIS.get(id_ponto)
            if not historico_ponto:
                print(f"ERRO: Falha ao reinicializar {id_ponto}");
                continue
        novos_dados_nesta_rodada = []
        historico_atualizado = list(historico_ponto)
        for i in range(PASSOS_POR_ATUALIZACAO):
            try:
                ultimo_timestamp_str = historico_atualizado[-1]['timestamp']
            except (IndexError, KeyError, ValueError) as e:
                print(f"ERRO no passo {i + 1}: Falha ao ler último timestamp do {id_ponto}: {e}. Pulando o resto.");
                break
            ultimo_timestamp = datetime.datetime.fromisoformat(ultimo_timestamp_str.replace('Z', '+00:00'))
            proximo_timestamp = ultimo_timestamp + FREQUENCIA_SIMULACAO
            novo_dado = simulador.gerar_novo_dado(proximo_timestamp, historico_atualizado)
            novos_dados_nesta_rodada.append(novo_dado)
            historico_atualizado.append(novo_dado)
            total_novos_pontos_gerados += 1
        DADOS_HISTORICOS_GLOBAIS[id_ponto].extend(novos_dados_nesta_rodada)
        DADOS_HISTORICOS_GLOBAIS[id_ponto] = DADOS_HISTORICOS_GLOBAIS[id_ponto][-MAX_HISTORY_POINTS:]
        df_ponto = pd.DataFrame(DADOS_HISTORICOS_GLOBAIS[id_ponto]);
        df_ponto['id_ponto'] = id_ponto;
        dfs_de_todos_os_pontos.append(df_ponto)
    if not dfs_de_todos_os_pontos:
        colunas_finais = ['id_ponto', 'timestamp', 'chuva_mm', 'precipitacao_acumulada_mm', 'umidade_1m_perc',
                          'umidade_2m_perc', 'umidade_3m_perc', 'base_1m', 'base_2m', 'base_3m'];
        return pd.DataFrame(columns=colunas_finais)
    df_final = pd.concat(dfs_de_todos_os_pontos, ignore_index=True);
    df_final['timestamp'] = pd.to_datetime(df_final['timestamp']);
    df_final = df_final.rename(columns={'pluviometria_mm': 'chuva_mm'})
    colunas_finais = ['id_ponto', 'timestamp', 'chuva_mm', 'precipitacao_acumulada_mm', 'umidade_1m_perc',
                      'umidade_2m_perc', 'umidade_3m_perc', 'base_1m', 'base_2m', 'base_3m'];
    df_final = df_final[[col for col in colunas_finais if col in df_final.columns]];
    return df_final


def get_data():
    USA_API_REAL = False
    if USA_API_REAL:
        try:
            return get_dados_reais_zentra()
        except Exception as e:
            print(f"CRÍTICO: Falha API: {e}");
            return get_dados_simulados()
    else:
        return get_dados_simulados()