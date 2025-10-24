# processamento.py (CORRIGIDO com Gatilho de Alerta de Umidade MAIS ALTO)

import pandas as pd
import datetime

# --- Constantes para a Chuva (ALINHADAS COM map_view.py) ---
CHUVA_LIMITE_VERDE = 50.0  # Até 50mm
CHUVA_LIMITE_AMARELO = 69.0  # De 50.1mm a 69mm
CHUVA_LIMITE_LARANJA = 89.0  # De 69.1mm a 89mm
# Acima de 89mm é PARALISAÇÃO

# --- Constantes para a Umidade ---
TOLERANCIA_SECO = 0.1  # Margem para considerar um sensor "seco" (ex: base + 0.1%)

# --- INÍCIO DA ALTERAÇÃO (Gatilho Atrasado MAIS ALTO) ---
UMIDADE_SATURACAO_PADRAO = 45.0
GATILHO_ALERTA_UMIDADE_PERC = 0.75  # <-- ALTERADO PARA 75%
# --- FIM DA ALTERAÇÃO ---


# Mapeamento de Risco (Usado internamente)
RISCO_MAP = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3}
STATUS_MAP_HIERARQUICO = {
    3: ("PARALIZAÇÃO", "danger", "bg-danger"),
    2: ("ALERTA", "orange", "bg-orange"),
    1: ("ATENÇÃO", "warning", "bg-warning"),
    0: ("LIVRE", "success", "bg-success"),
    -1: ("SEM DADOS", "secondary", "bg-secondary")
}


# --- FUNÇÃO calcular_acumulado_72h (Mantida) ---
def calcular_acumulado_72h(df_ponto):
    """
    Calcula o acumulado de chuva de 72 horas (janela deslizante)
    para um DataFrame de PONTO ÚNICO.
    """
    if 'chuva_mm' not in df_ponto.columns or df_ponto.empty or 'timestamp' not in df_ponto.columns:
        return pd.DataFrame(columns=['timestamp', 'chuva_mm'])
    df = df_ponto.sort_values('timestamp').copy()
    df = df.set_index('timestamp')
    try:
        acumulado_72h = df['chuva_mm'].rolling(window='72h', min_periods=1).sum()
        acumulado_72h = acumulado_72h.rename('chuva_mm')
        return acumulado_72h.reset_index()
    except Exception as e:
        print(f"Erro ao calcular acumulado 72h com rolling window: {e}")
        return pd.DataFrame(columns=['timestamp', 'chuva_mm'])


# --- FUNÇÃO definir_status_chuva (Mantida) ---
def definir_status_chuva(chuva_mm):
    """
    Define o status (texto) e a cor (para badge) da chuva com base nos limites.
    """
    STATUS_MAP_CHUVA = {"LIVRE": "success", "ATENÇÃO": "warning", "ALERTA": "orange", "PARALIZAÇÃO": "danger",
                        "SEM DADOS": "secondary", "INDEFINIDO": "secondary"}
    try:
        if pd.isna(chuva_mm):
            status_texto = "SEM DADOS"
        elif chuva_mm >= 90.0:
            status_texto = "PARALIZAÇÃO"
        elif chuva_mm > CHUVA_LIMITE_LARANJA:
            status_texto = "PARALIZAÇÃO"
        elif chuva_mm > CHUVA_LIMITE_AMARELO:
            status_texto = "ALERTA"
        elif chuva_mm > CHUVA_LIMITE_VERDE:
            status_texto = "ATENÇÃO"
        else:
            status_texto = "LIVRE"
        return status_texto, STATUS_MAP_CHUVA.get(status_texto, "secondary")
    except Exception as e:
        print(f"Erro status chuva: {e}");
        return "INDEFINIDO", "secondary"


# --- FUNÇÃO definir_status_umidade_hierarquico (Gatilho Alterado) ---
def definir_status_umidade_hierarquico(umidade_1m, umidade_2m, umidade_3m, base_1m, base_2m, base_3m):
    """
    Define o status/cor de alerta com base em QUÃO MOLHADO cada sensor está
    em relação à sua faixa (base -> saturação), usando um GATILHO ALTO (75%).
    Retorna (texto_status, cor_badge, cor_barra_css).
    """
    try:
        if pd.isna(umidade_1m) or pd.isna(umidade_2m) or pd.isna(umidade_3m):
            return STATUS_MAP_HIERARQUICO[-1]  # ("SEM DADOS", "secondary", "bg-secondary")

        saturacao_1m = UMIDADE_SATURACAO_PADRAO
        saturacao_2m = UMIDADE_SATURACAO_PADRAO
        saturacao_3m = UMIDADE_SATURACAO_PADRAO

        faixa_1m = max(0.1, saturacao_1m - base_1m)
        faixa_2m = max(0.1, saturacao_2m - base_2m)
        faixa_3m = max(0.1, saturacao_3m - base_3m)

        # Usa o GATILHO_ALERTA_UMIDADE_PERC (agora 0.75)
        gatilho_1m = base_1m + GATILHO_ALERTA_UMIDADE_PERC * faixa_1m
        gatilho_2m = base_2m + GATILHO_ALERTA_UMIDADE_PERC * faixa_2m
        gatilho_3m = base_3m + GATILHO_ALERTA_UMIDADE_PERC * faixa_3m

        s1_ativo = umidade_1m >= gatilho_1m
        s2_ativo = umidade_2m >= gatilho_2m
        s3_ativo = umidade_3m >= gatilho_3m

        risco_final = 0  # Começa Livre

        # Lógica hierárquica baseada nos gatilhos (mais altos agora)
        if s3_ativo:
            risco_final = 3  # PARALIZAÇÃO
        elif s2_ativo:
            risco_final = 2  # ALERTA
        elif s1_ativo:
            risco_final = 1  # ATENÇÃO

        return STATUS_MAP_HIERARQUICO[risco_final]

    except Exception as e:
        print(f"Erro ao definir status de umidade hierárquico: {e}")
        return STATUS_MAP_HIERARQUICO[-1]