# alertas.py (CORRIGIDO - Definição de Variáveis Globais e Lógica de Isolamento)

import httpx
import os
import requests
import json  # Adicionado para garantir compatibilidade se usado

# --- Constantes da API SMTP2GO ---
SMTP2GO_API_URL = "https://api.smtp2go.com/v3/email/send"

# --- Variáveis de Ambiente (E-MAIL) - LENDO DO OS.ENVIRON ---
SMTP2GO_API_KEY = os.environ.get('SMTP2GO_API_KEY')
SMTP2GO_SENDER_EMAIL = os.environ.get('SMTP2GO_SENDER_EMAIL')
DESTINATARIOS_EMAIL_STR = os.environ.get('DESTINATARIOS_EMAIL')

# --- Variáveis de Ambiente (SMS - COMTELE) - LENDO DO OS.ENVIRON ---
COMTELE_API_KEY = os.environ.get('COMTELE_API_KEY')
SMS_DESTINATARIOS_STR = os.environ.get('SMS_DESTINATARIOS')


# --- Função Helper de E-mail (SMTP2GO) ---
def _enviar_email_smtp2go(api_key, sender_email, recipients_list, subject, html_body):
    """ Envia um e-mail usando a API HTTP da SMTP2GO. """

    # Mapeia a cor bootstrap para uma cor CSS
    cor_css = "grey"
    if 'danger' in subject.upper():
        cor_css = "#dc3545"  # Vermelho
    elif 'success' in subject.upper():
        cor_css = "#28a745"  # Verde

    payload = {
        "api_key": api_key,
        "sender": sender_email,
        "to": recipients_list,
        "subject": subject,
        "html_body": f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h1 style='color: {cor_css};'>Alerta de Risco: {subject.split(':')[-1].strip()}</h1>
                <p>O sistema de monitoramento detectou uma mudança de status no ponto:</p>
                <p>{html_body}</p>
                <p style="font-size: 0.8em; color: #777;">Este é um e-mail automático.</p>
            </body>
            </html>
            """,
        "text_body": "Por favor, habilite o HTML para ver esta mensagem de alerta."
    }
    headers = {"Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(SMTP2GO_API_URL, headers=headers, json=payload)

        # Tratamento de erro SMTP2GO
        if response.status_code == 200 and response.json().get('data', {}).get('failures', 1) == 0:
            print(f"E-mail de alerta (SMTP2GO) enviado com sucesso para: {recipients_list}")
        else:
            # Levanta exceção para que a função chamadora saiba que o E-mail falhou
            print(f"ERRO API SMTP2GO (E-mail): {response.status_code} - {response.text}")
            raise Exception(f"Falha no envio SMTP2GO: {response.text}")

    except httpx.RequestError as e:
        print(f"ERRO HTTX (E-mail): Falha ao conectar à API SMTP2GO. {e}")
        raise Exception(f"ERRO HTTX (E-mail): Falha de Conexão.")
    except Exception as e:
        raise e


# --- Nova Função Helper de SMS (COMTELE - COM LOG DETALHADO) ---
def _enviar_sms_comtele(api_key, recipients_list, message):
    """ Envia SMS usando a API da Comtele e imprime a resposta detalhada em caso de falha. """
    # URL CORRETA DA COMTELE
    COMTELE_API_URL = "https://sms.comtele.com.br/api/v2/send"

    if not api_key:
        # Não levanta erro fatal, mas avisa
        print("ALERTA SMS (Ignorado): COMTELE_API_KEY não configurada.")
        return

    # A Comtele espera um único campo 'Receivers' com os números separados por vírgula
    numeros_com_virgula = ",".join(recipients_list)

    payload = {
        "Content": message,
        "Receivers": numeros_com_virgula
    }

    headers = {
        "auth-key": api_key,  # Chave de autorização no Header
        "Content-Type": "application/json"
    }

    print(f"--- Tentando enviar SMS (Comtele) para: {numeros_com_virgula} ---")

    try:
        response = requests.post(COMTELE_API_URL, headers=headers, json=payload, timeout=10.0)

        # Tenta ler o JSON da resposta para verificar 'Success'
        try:
            resposta_json = response.json()
            success = resposta_json.get('Success', False)
        except requests.exceptions.JSONDecodeError:
            success = False
            # Caso a API retorne algo que não é JSON (ex: erro de gateway)
            resposta_json = {"Message": "Resposta não-JSON ou erro de decodificação."}

        # Verifica se a API retornou sucesso E se o status HTTP é aceitável
        if response.status_code == 200 and success:
            print(f"SMS de alerta (Comtele) enviado com sucesso para: {numeros_com_virgula}")
        else:
            # Se falhou, levanta uma exceção com o detalhe para o chamador
            print(f"!!! FALHA NO ENVIO SMS (Comtele) !!! Status HTTP: {response.status_code}")
            raise Exception(f"Falha Comtele. Status {response.status_code}. Resposta: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"ERRO DE CONEXÃO (Comtele SMS): Falha ao conectar à API Comtele. {e}")
        raise Exception(f"ERRO DE CONEXÃO (Comtele SMS): Falha de Conexão.")
    except Exception as e:
        raise e


# --- FUNÇÃO UNIFICADA (ISOLANDO FALHAS) ---
def enviar_alerta(id_ponto, nome_ponto, novo_status, cor_status):
    """
    Função principal de alerta. Tenta enviar E-mail e SMS de forma INDEPENDENTE.
    Levanta exceção APENAS se todos os métodos configurados falharem.
    """

    # 1. Preparar Conteúdo
    # ... (código para preparar assunto_email, html_body_part, sms_mensagem, status_log)
    if novo_status == "PARALIZAÇÃO TOTAL":
        status_log = "PARALIZAÇÃO TOTAL"
        assunto_email = f"ALERTA CRÍTICO: PARALIZAÇÃO TOTAL"
        html_body_part = f"""
            <p>O sistema de monitoramento detectou que <strong>TODOS OS PONTOS</strong> entraram na condição de <strong>PARALIZAÇÃO TOTAL</strong>.</p>
            <p><strong>Ponto de Referência: {nome_ponto}</strong></p>
            <p>Ação Imediata é requerida. Por favor, verifique o dashboard.</p>
            """
        sms_mensagem = f"ALERTA CRITICO: PARALIZACAO TOTAL DA VIA. Acao imediata e requerida. Verifique o sistema."

    elif novo_status == "SISTEMA NORMALIZADO":
        status_log = "SISTEMA NORMALIZADO"
        assunto_email = f"AVISO: SISTEMA DE MONITORAMENTO NORMALIZADO"
        html_body_part = f"""
            <p>O sistema de monitoramento detectou que a condição de <strong>PARALIZAÇÃO TOTAL</strong> foi encerrada. Os pontos estão fora do risco mais alto.</p>
            <p>Ponto de Referência: {nome_ponto}</p>
            """
        sms_mensagem = f"AVISO: Sistema de Monitoramento NORMALIZADO. Condicao de risco alto encerrada."
    else:
        return

    sucesso_email = False
    sucesso_sms = False

    # 2. Envio de E-mail (Isolado)
    if SMTP2GO_API_KEY and SMTP2GO_SENDER_EMAIL and DESTINATARIOS_EMAIL_STR:
        destinatarios_email = [email.strip() for email in DESTINATARIOS_EMAIL_STR.split(',')]
        if destinatarios_email:
            try:
                _enviar_email_smtp2go(SMTP2GO_API_KEY, SMTP2GO_SENDER_EMAIL, destinatarios_email, assunto_email,
                                      html_body_part)
                sucesso_email = True
            except Exception as e:
                print(f"FALHA ISOLADA: Envio de E-mail (SMTP2GO) falhou: {e}")
    else:
        print(f"AVISO: Envio de E-mail ({status_log}) não configurado ou com chaves faltando.")

    # 3. Envio de SMS (Comtele - Isolado)
    if COMTELE_API_KEY and SMS_DESTINATARIOS_STR:
        destinatarios_sms = [num.strip() for num in SMS_DESTINATARIOS_STR.split(',')]
        if destinatarios_sms:
            try:
                _enviar_sms_comtele(COMTELE_API_KEY, destinatarios_sms, sms_mensagem)
                sucesso_sms = True
            except Exception as e:
                print(f"FALHA ISOLADA: Envio de SMS (Comtele) falhou: {e}")
    else:
        print(f"AVISO: Envio de SMS ({status_log}) não configurado ou com chaves faltando.")

    # 4. Verificação Final e Levantamento de Erro ÚNICO
    # A falha total só ocorre se TODOS os métodos de notificação configurados falharem.

    email_configurado = bool(SMTP2GO_API_KEY and SMTP2GO_SENDER_EMAIL and DESTINATARIOS_EMAIL_STR)
    sms_configurado = bool(COMTELE_API_KEY and SMS_DESTINATARIOS_STR)

    if (email_configurado and not sucesso_email) and (sms_configurado and not sucesso_sms):
        raise Exception("ALERTA CRÍTICO: Falha total na notificação (Email e SMS).")

    if (email_configurado and not sucesso_email) and (not sms_configurado):
        # Falha no E-mail (único método configurado)
        raise Exception("ALERTA CRÍTICO: Falha total na notificação (Email).")

    if (sms_configurado and not sucesso_sms) and (not email_configurado):
        # Falha no SMS (único método configurado)
        raise Exception("ALERTA CRÍTICO: Falha total na notificação (SMS).")

    # Se pelo menos um estava configurado E funcionou, ou se nada estava configurado (o que não deve acontecer), retorna normalmente.
    return