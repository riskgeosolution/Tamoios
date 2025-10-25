# processamento.py (CORRIGIDO - Garante mapeamento correto)

import pandas as pd
import datetime

# --- Constantes para a Chuva (Mantidas) ---
CHUVA_LIMITE_VERDE = 50.0
CHUVA_LIMITE_AMARELO = 69.0
CHUVA_LIMITE_LARANJA = 89.0

# --- Constantes para a Umidade ---
TOLERANCIA_SECO = 0.1
DELTA_TRIGGER_UMIDADE = 5.0

# Mapeamento de Risco (Usado internamente aqui)
RISCO_MAP = {"LIVRE": 0, "ATENÇÃO": 1, "ALERTA": 2, "PARALIZAÇÃO": 3, "SEM DADOS": -1}

# --- INÍCIO DA CORREÇÃO: Mapeamento de Status ---
# Garante que os nomes de status padrão correspondam aos riscos corretos
STATUS_MAP_HIERARQUICO = {
    3: ("PARALIZAÇÃO", "danger", "bg-danger"),  # Risco 3 (Vermelho)
    2: ("ALERTA", "orange", "bg-orange"),  # Risco 2 (Laranja)
    1: ("ATENÇÃO", "warning", "bg-warning"),  # Risco 1 (Amarelo/Ouro - CSS define .bg-warning)
    0: ("LIVRE", "success", "bg-success"),  # Risco 0 (Verde)
    -1: ("SEM DADOS", "secondary", "bg-secondary")  # Risco -1
}
STATUS_MAP_FLUXOGRAMA = STATUS_MAP_HIERARQUICO  # Alias


# --- FIM DA CORREÇÃO ---


# --- FUNÇÃO calcular_acumulado_72h (Mantida) ---
# ... (código mantido) ...
def calcular_acumulado_72h(df_ponto):
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
    # ... (código mantido) ...
    STATUS_MAP_CHUVA = {"LIVRE": "success", "ATENÇÃO": "warning", "ALERTA": "orange", "PARALIZAÇÃO": "danger",
                        "SEM DADOS": "secondary", "INDEFINIDO": "secondary"}
    try:
        if pd.isna(chuva_mm):
            status_texto = "SEM DADOS"
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


# --- FUNÇÃO definir_status_umidade_hierarquico (Lógica do Fluxograma, Mantida) ---
def definir_status_umidade_hierarquico(umidade_1m, umidade_2m, umidade_3m,
                                       base_1m, base_2m, base_3m,
                                       chuva_acumulada_72h=0.0):
    # ... (código mantido) ...
    try:
        if pd.isna(umidade_1m) or pd.isna(umidade_2m) or pd.isna(umidade_3m):
            return STATUS_MAP_HIERARQUICO[-1]
        s1_sim = (umidade_1m - base_1m) >= DELTA_TRIGGER_UMIDADE
        s2_sim = (umidade_2m - base_2m) >= DELTA_TRIGGER_UMIDADE
        s3_sim = (umidade_3m - base_3m) >= DELTA_TRIGGER_UMIDADE
        risco_final = 0
        if s1_sim and s2_sim and s3_sim:
            risco_final = 3
        elif (s1_sim and s2_sim and not s3_sim) or (not s1_sim and not s2_sim and s3_sim):
            risco_final = 2
        elif (s1_sim and not s2_sim and not s3_sim) or (not s1_sim and s2_sim and s3_sim):
            risco_final = 1
        return STATUS_MAP_HIERARQUICO[risco_final]
    except Exception as e:
        print(f"Erro ao definir status de umidade (fluxograma): {e}")
        return STATUS_MAP_HIERARQUICO[-1]


# --- FUNÇÃO definir_status_umidade_individual (CORRIGIDA) ---
def definir_status_umidade_individual(umidade_atual, umidade_base, risco_nivel):
    """
    Define a cor CSS para um ÚNICO sensor.
    Usa o nível de risco (1, 2, 3) para determinar a cor (Amarelo, Laranja, Vermelho)
    se o sensor estiver ativo (delta >= 5%).
    """
    try:
        if pd.isna(umidade_atual) or pd.isna(umidade_base):
            return "grey"  # Sem Dados

        if (umidade_atual - umidade_base) >= DELTA_TRIGGER_UMIDADE:
            # Se o delta é >= 5%, o sensor está "ativo".
            # --- INÍCIO DA CORREÇÃO: Mapeia Risco para Cor CSS ---
            if risco_nivel == 1:
                return "#FFD700"  # Amarelo/Ouro (Atenção)
            elif risco_nivel == 2:
                return "#fd7e14"  # Laranja (Alerta)
            elif risco_nivel == 3:
                return "#dc3545"  # Vermelho (Paralisação)
            else:
                return "#FFD700"  # Default para Amarelo se ativo
            # --- FIM DA CORREÇÃO ---
        else:
            # Se está abaixo do gatilho, está "Livre"
            return "green"  # Verde/Livre

    except Exception:
        return "grey"