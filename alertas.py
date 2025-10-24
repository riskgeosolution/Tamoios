# alertas.py (Modificado)
import httpx
import os


# ... (leitura das variáveis de ambiente COMTELE_API_KEY, etc.) ...

def enviar_alerta(id_ponto, nome_ponto, novo_status, cor_status):
    """
    Função principal de alerta. Decide se envia SMS e/ou Email.
    AGORA INCLUI O PONTO DE ORIGEM.
    """
    if not COMTELE_API_KEY:
        print(f"ALERTA (Ignorado): COMTELE_API_KEY não configurada.")
        return

    # Só envie alertas para status de risco
    if novo_status not in ["ATENÇÃO", "PARALIZAR"]:
        print(f"Ponto {id_ponto}: Status '{novo_status}' não requer alerta.")
        return

    # Monta a mensagem específica do ponto
    mensagem_simples = f"[ALERTA: {nome_ponto}] O status do sensor mudou para: {novo_status}"

    # 1. Tenta enviar SMS
    if DESTINATARIOS_SMS and DESTINATARIOS_SMS[0]:
        print(f"Enviando SMS para: {DESTINATARIOS_SMS}")
        try:
            _enviar_sms_comtele(mensagem_simples, DESTINATARIOS_SMS)
        except Exception as e:
            print(f"ERRO AO ENVIAR SMS COMTELE: {e}")

    # 2. Tenta enviar Email
    if DESTINATARIOS_EMAIL and DESTINATARIOS_EMAIL[0]:
        print(f"Enviando Email para: {DESTINATARIOS_EMAIL}")
        try:
            assunto_email = f"[ALERTA: {novo_status}] Monitoramento - {nome_ponto}"
            conteudo_email = f"""
            <html>
            <body>
                <h1 style='color: {cor_status};'>Alerta de Risco: {novo_status}</h1>
                <p>O sistema de monitoramento detectou uma mudança de status no ponto:</p>
                <p><strong>Ponto: {nome_ponto} ({id_ponto})</strong></p>
                <p><strong>Novo Status: {novo_status}</strong></p>
                <p>Por favor, verifique o dashboard para mais detalhes.</p>
            </body>
            </html>
            """
            _enviar_email_comtele(assunto_email, conteudo_email, DESTINATARIOS_EMAIL)
        except Exception as e:
            print(f"ERRO AO ENVIAR EMAIL COMTELE: {e}")

# ... (funções _enviar_sms_comtele e _enviar_email_comtele permanecem iguais) ...