from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import os
import datetime
import traceback # Importado para depuração de erros

app = Flask(__name__)
# Habilita CORS para todas as rotas da sua aplicação Flask
# Esta configuração é mais flexível para testes locais em múltiplos computadores.
# ATENÇÃO: PARA PRODUÇÃO, RECOMENDA-SE RESTRINGIR AS ORIGENS O MÁXIMO POSSÍVEL.
CORS(app, resources={r"/*": {"origins": [
    "http://localhost:5500",  # Sua máquina (Live Server)
    "http://127.0.0.1:5500",  # Sua máquina (Live Server)
    "http://localhost:5000",  # Porta padrão do Flask se rodar sem Live Server
    "http://127.0.0.1:5501",  # Porta padrão do Flask
    "file://",                # Para arquivos HTML abertos diretamente do disco
    "null"                    # Outra origem para arquivos abertos diretamente do disco (Chrome)
]}})

# Suas credenciais e URLs da Cielo, agora carregadas de variáveis de ambiente
# O segundo argumento de os.getenv() é um valor padrão para uso local,
# caso as variáveis de ambiente não estejam definidas no seu sistema.
# No Render, você definirá essas variáveis na interface.
MERCHANT_ID = os.getenv("CIELO_MERCHANT_ID", "6542d0f6-f606-440b-a96e-7fd5a4ec8155")
MERCHANT_KEY = os.getenv("CIELO_MERCHANT_KEY", "eVMfHMRlgw0oQAMTHUI5PrfO22ub03TBvISo3oEF")

# URLs da API Cielo (ATENÇÃO: VERIFIQUE SE SÃO DE SANDBOX OU PRODUÇÃO NO RENDER!)
CIELO_API_URL = os.getenv("CIELO_API_URL", "https://api.cieloecommerce.cielo.com.br/1/sales/")
CIELO_API_QUERY_URL = os.getenv("CIELO_API_QUERY_URL", "https://apiquery.cieloecommerce.cielo.com.br/1/sales/")

@app.route('/')
def home():
    return "Backend Cielo funcionando! Acesse /processar-pagamento, /processar-pix ou /processar-boleto."

# --- ROTA PARA CARTÃO DE CRÉDITO ---
@app.route('/processar-pagamento', methods=['POST'])
def processar_pagamento():
    try:
        data = request.get_json()

        # Verifica se 'data' é None ou não é um dicionário
        if not isinstance(data, dict) or not data:
            print(f"Erro: Payload JSON recebido não é um dicionário ou está vazio. Tipo: {type(data)}")
            return jsonify({"error": "Dados inválidos ou incompletos. Esperado um objeto JSON."}), 400

        if 'paymentDetails' not in data or 'billingData' not in data:
            return jsonify({"error": "Dados inválidos ou incompletos"}), 400

        payment_details = data['paymentDetails']
        billing_data = data['billingData']

        # Validação básica dos campos de pagamento de cartão
        if 'cardNumber' not in payment_details or 'holder' not in payment_details or \
           'expirationDate' not in payment_details or 'securityCode' not in payment_details or \
           'amount' not in payment_details:
            return jsonify({"error": "Dados de pagamento do cartão incompletos"}), 400

        card_number = payment_details['cardNumber'].replace(" ", "").replace("-", "")
        amount_in_cents = int(float(payment_details['amount']) * 100)
        installments = payment_details.get('installments', 1) # Pega do front-end, padrão 1

        # MerchantOrderId deve ser único para cada transação. Geraremos um dinamicamente.
        merchant_order_id = f"LV_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

        payment_data = {
            "MerchantOrderId": merchant_order_id,
            "Customer": {
                "Name": f"{billing_data.get('firstName')} {billing_data.get('lastName')}",
                "Identity": billing_data.get('cpf'),
                "IdentityType": "CPF",
                "Email": billing_data.get('email'),
                "Address": {
                    "Street": billing_data.get('address'),
                    "Number": billing_data.get('number'),
                    "Complement": billing_data.get('complement'),
                    "ZipCode": billing_data.get('zipCode'),
                    "District": billing_data.get('neighborhood'),
                    # IMPORTANTE: Garanta que 'city' e 'state' venham do frontend ou use padrões robustos.
                    "City": billing_data.get('city', 'SAO PAULO'), # Sugestão: adicione 'city' ao billingData do frontend
                    "State": billing_data.get('state', 'SP'),     # Sugestão: adicione 'state' ao billingData do frontend
                    "Country": billing_data.get('country', 'BRA')
                },
                "DeliveryAddress": { # Pode ser o mesmo do cliente, se não houver um endereço de entrega separado
                    "Street": billing_data.get('address'),
                    "Number": billing_data.get('number'),
                    "Complement": billing_data.get('complement'),
                    "ZipCode": billing_data.get('zipCode'),
                    "District": billing_data.get('neighborhood'),
                    # CORRIGIDO: Preencha com valores reais para testes.
                    "City": billing_data.get('city', 'SAO PAULO'),
                    "State": billing_data.get('state', 'SP'),
                    "Country": billing_data.get('country', 'BRA')
                }
            },
            "Payment": {
                "Type": "CreditCard",
                "Amount": amount_in_cents,
                "Installments": installments,
                "SoftDescriptor": "LIVRARIAWEB",
                "Capture": True, # Geralmente, para cartão de crédito, você quer capturar na autorização
                "CreditCard": {
                    "CardNumber": card_number,
                    "Holder": payment_details['holder'],
                    # A data de validade deve ser MM/AAAA (do frontend)
                    # Cielo espera MMYYYY ou MM/YY ou MM/YYYY.
                    # Mantenha o formato que vem do frontend, se o erro persistir, ajuste no frontend para MMAAAA.
                    "ExpirationDate": payment_details['expirationDate'],
                    "SecurityCode": payment_details['securityCode'],
                    "Brand": "Visa" # A Cielo pode auto-detectar, mas é bom enviar. Em produção, você pode usar a detecção de bin.
                }
            }
        }

        headers = {
            "Content-Type": "application/json",
            "MerchantId": MERCHANT_ID,
            "MerchantKey": MERCHANT_KEY
        }

        print(f"Enviando para Cielo (Cartão): {json.dumps(payment_data, indent=2)}")

        response = requests.post(CIELO_API_URL, headers=headers, data=json.dumps(payment_data))
        
        # --- Tratamento de erro para resposta não-JSON ---
        try:
            response_json = response.json()
        except json.JSONDecodeError:
            print(f"Erro: Resposta da Cielo não é JSON válido. Status: {response.status_code}, Conteúdo: {response.text}")
            return jsonify({
                "status": "error",
                "message": f"Erro inesperado da Cielo. Status: {response.status_code}. Conteúdo: {response.text[:200]}...",
                "cielo_error": {"raw_response": response.text, "status_code": response.status_code}
            }), 502 # 502 Bad Gateway indica que o servidor recebeu uma resposta inválida de outro servidor
        # --- FIM DO BLOCO DE TRATAMENTO DE JSON ---

        print(f"Resposta da Cielo (Cartão): {json.dumps(response_json, indent=2)}")

        # --- MODIFICAÇÃO PRINCIPAL: Trata respostas de erro da Cielo que são LISTAS ---
        if isinstance(response_json, list) and response_json: # Se a resposta é uma lista e não está vazia
            first_error = response_json[0]
            error_message = first_error.get('Message', 'Erro desconhecido na lista de erros da Cielo')
            error_code = first_error.get('Code', 'N/A')
            return jsonify({
                "status": "error",
                "message": f"Erro da Cielo: {error_message} (Código: {error_code})",
                "cielo_error": response_json
            }), response.status_code # Usamos o status code original da resposta da Cielo

        # Continua com a lógica normal para respostas que são dicionários
        # A Cielo retorna 201 Created para sucesso de autorização, e Status 2 para Autorizado
        if response.status_code == 201 and response_json.get('Payment', {}).get('Status') == 2:
            return jsonify({
                "status": "success",
                "message": "Pagamento com cartão processado com sucesso!",
                "cielo_response": response_json
            }), 200
        else:
            # Caso a resposta seja um dicionário mas contenha um erro ou status diferente
            return jsonify({
                "status": "error",
                "message": response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar pagamento com cartão na Cielo'),
                "cielo_error": response_json
            }), response.status_code

    except Exception as e:
        # Captura qualquer outra exceção e imprime o traceback completo
        print(f"Erro INESPERADO na rota do CARTÃO: {type(e).__name__}: {e}")
        print("Detalhes completos do traceback:")
        traceback.print_exc() # Imprime a pilha de chamadas completa no log
        return jsonify({"status": "error", "message": f"Erro interno no backend. Detalhes: {str(e)}", "exception_type": type(e).__name__}), 500


# --- ROTA PARA CARTÃO DE DÉBITO ---
@app.route('/processar-debito', methods=['POST'])
def processar_debito():
    try:
        data = request.get_json()

        if not isinstance(data, dict) or not data:
            print(f"Erro: Payload JSON recebido não é um dicionário ou está vazio. Tipo: {type(data)}")
            return jsonify({"error": "Dados inválidos ou incompletos. Esperado um objeto JSON."}), 400

        if 'paymentDetails' not in data or 'billingData' not in data:
            return jsonify({"error": "Dados inválidos ou incompletos"}), 400

        payment_details = data['paymentDetails']
        billing_data = data['billingData']

        # Validação básica dos campos de pagamento de débito
        if 'cardNumber' not in payment_details or 'holder' not in payment_details or \
           'expirationDate' not in payment_details or 'securityCode' not in payment_details or \
           'amount' not in payment_details:
            return jsonify({"error": "Dados de pagamento do cartão de débito incompletos"}), 400

        card_number = payment_details['cardNumber'].replace(" ", "").replace("-", "")
        amount_in_cents = int(float(payment_details['amount']) * 100)

        merchant_order_id = f"LV_DEBITO_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

        debit_data = {
            "MerchantOrderId": merchant_order_id,
            "Customer": {
                "Name": f"{billing_data.get('firstName')} {billing_data.get('lastName')}",
                "Identity": billing_data.get('cpf'),
                "IdentityType": "CPF",
                "Email": billing_data.get('email'),
                "Address": {
                    "Street": billing_data.get('address'),
                    "Number": billing_data.get('number'),
                    "Complement": billing_data.get('complement'),
                    "ZipCode": billing_data.get('zipCode'),
                    "District": billing_data.get('neighborhood'),
                    "City": billing_data.get('city', 'SAO PAULO'),
                    "State": billing_data.get('state', 'SP'),
                    "Country": billing_data.get('country', 'BRA')
                },
                "DeliveryAddress": {
                    "Street": billing_data.get('address'),
                    "Number": billing_data.get('number'),
                    "Complement": billing_data.get('complement'),
                    "ZipCode": billing_data.get('zipCode'),
                    "District": billing_data.get('neighborhood'),
                    "City": billing_data.get('city', 'SAO PAULO'),
                    "State": billing_data.get('state', 'SP'),
                    "Country": billing_data.get('country', 'BRA')
                }
            },
            "Payment": {
                "Type": "DebitCard", # Tipo de pagamento para Cartão de Débito
                "Amount": amount_in_cents,
                "Authenticate": True, # Débito geralmente exige autenticação 3DS
                # ATENÇÃO: Esta ReturnUrl é para o frontend local.
                # Em produção, deve ser a URL do seu frontend em produção (ex: https://sua-loja.com/finalizar.html)
                "ReturnUrl": "http://localhost:5500/Front%20end/finalizar.html", 
                "SoftDescriptor": "LIVRARIAWEB",
                "DebitCard": {
                    "CardNumber": card_number,
                    "Holder": payment_details['holder'],
                    "ExpirationDate": payment_details['expirationDate'], # MM/AAAA ou MMAAAA (conforme frontend)
                    "SecurityCode": payment_details['securityCode'],
                    "Brand": "Visa" # Ou a bandeira correta
                }
            }
        }

        headers = {
            "Content-Type": "application/json",
            "MerchantId": MERCHANT_ID,
            "MerchantKey": MERCHANT_KEY
        }

        print(f"Enviando para Cielo (Débito): {json.dumps(debit_data, indent=2)}")

        response = requests.post(CIELO_API_URL, headers=headers, data=json.dumps(debit_data))
        
        try:
            response_json = response.json()
        except json.JSONDecodeError:
            print(f"Erro: Resposta da Cielo (Débito) não é JSON válido. Status: {response.status_code}, Conteúdo: {response.text}")
            return jsonify({
                "status": "error",
                "message": f"Erro inesperado da Cielo. Status: {response.status_code}. Conteúdo: {response.text[:200]}...",
                "cielo_error": {"raw_response": response.text, "status_code": response.status_code}
            }), 502

        print(f"Resposta da Cielo (Débito): {json.dumps(response_json, indent=2)}")

        # A Cielo retorna 201 Created para sucesso de criação da transação de débito
        if response.status_code == 201 and response_json.get('Payment', {}).get('AuthenticationUrl'):
            # Se a URL de autenticação 3DS foi retornada, redirecionar o cliente para lá
            return jsonify({
                "status": "success",
                "message": "Redirecionando para autenticação 3D Secure...",
                "cielo_response": response_json,
                "redirect_url": response_json['Payment']['AuthenticationUrl'] # O frontend usará esta URL
            }), 200
        elif isinstance(response_json, list) and response_json: # Trata erros que vêm como lista
            first_error = response_json[0]
            error_message = first_error.get('Message', 'Erro desconhecido na lista de erros da Cielo (Débito)')
            error_code = first_error.get('Code', 'N/A')
            return jsonify({
                "status": "error",
                "message": f"Erro da Cielo (Débito): {error_message} (Código: {error_code})",
                "cielo_error": response_json
            }), response.status_code
        else:
            return jsonify({
                "status": "error",
                "message": response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar débito na Cielo'),
                "cielo_error": response_json
            }), response.status_code

    except Exception as e:
        print(f"Erro INESPERADO na rota do DÉBITO: {type(e).__name__}: {e}")
        print("Detalhes completos do traceback:")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro interno no backend. Detalhes: {str(e)}", "exception_type": type(e).__name__}), 500


# --- ROTA PARA PIX ---
@app.route('/processar-pix', methods=['POST'])
def processar_pix():
    try:
        data = request.get_json()
        
        if not isinstance(data, dict) or not data:
            print(f"Erro: Payload JSON recebido não é um dicionário ou está vazio. Tipo: {type(data)}")
            return jsonify({"error": "Dados inválidos ou incompletos. Esperado um objeto JSON."}), 400

        if not data or 'paymentDetails' not in data or 'billingData' not in data:
            return jsonify({"error": "Dados inválidos ou incompletos"}), 400

        payment_details = data['paymentDetails'] # Contém amount, customer
        billing_data = data['billingData']

        amount_in_cents = int(float(payment_details['amount']) * 100)
        merchant_order_id = f"LV_PIX_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

        # Construa o payload para o Pix (Cielo espera um formato específico)
        pix_data = {
            "MerchantOrderId": merchant_order_id,
            "Customer": {
                "Name": f"{billing_data.get('firstName')} {billing_data.get('lastName')}",
                "Identity": billing_data.get('cpf'),
                "IdentityType": "CPF",
                "Email": billing_data.get('email')
            },
            "Payment": {
                "Type": "Pix",
                "Amount": amount_in_cents,
                "Pix": {
                    "ExpiresIn": 3600 # Validade do QR Code em segundos (1 hora)
                }
            }
        }

        headers = {
            "Content-Type": "application/json",
            "MerchantId": MERCHANT_ID,
            "MerchantKey": MERCHANT_KEY
        }

        print(f"Enviando para Cielo (Pix): {json.dumps(pix_data, indent=2)}")

        response = requests.post(CIELO_API_URL, headers=headers, data=json.dumps(pix_data))
        
        # --- Tratamento de erro para resposta não-JSON ---
        try:
            response_json = response.json()
        except json.JSONDecodeError:
            print(f"Erro: Resposta da Cielo não é JSON válido. Status: {response.status_code}, Conteúdo: {response.text}")
            return jsonify({
                "status": "error",
                "message": f"Erro inesperado da Cielo. Status: {response.status_code}. Conteúdo: {response.text[:200]}...",
                "cielo_error": {"raw_response": response.text, "status_code": response.status_code}
            }), 502
        # --- FIM DO BLOCO DE TRATAMENTO DE JSON ---

        print(f"Resposta da Cielo (Pix): {json.dumps(response_json, indent=2)}")

        # --- MODIFICAÇÃO PRINCIPAL: Trata respostas de erro da Cielo que são LISTAS ---
        if isinstance(response_json, list) and response_json:
            first_error = response_json[0]
            error_message = first_error.get('Message', 'Erro desconhecido na lista de erros da Cielo (Pix)')
            error_code = first_error.get('Code', 'N/A')
            return jsonify({
                "status": "error",
                "message": f"Erro da Cielo (Pix): {error_message} (Código: {error_code})",
                "cielo_error": response_json
            }), response.status_code

        if response.status_code == 201: # 201 Created é o esperado para sucesso na criação do Pix
            # Verifique se a string do QR Code está presente
            qr_code_string = response_json.get('Payment', {}).get('QrCodeString')
            qr_code_image_url = response_json.get('Payment', {}).get('QrCodeImageUrl') # URL da imagem do QR Code
            
            if qr_code_string:
                return jsonify({
                    "status": "success",
                    "message": "QR Code Pix gerado com sucesso!",
                    "cielo_response": response_json,
                    "qr_code_string": qr_code_string,
                    "qr_code_image_url": qr_code_image_url # Envia a URL da imagem (se houver)
                }), 200
            else:
                return jsonify({
                    "status": "error",
                    "message": "Erro ao gerar QR Code Pix: QR Code não encontrado na resposta.",
                    "cielo_error": response_json
                }), response.status_code
        else:
            return jsonify({
                "status": "error",
                "message": response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar Pix na Cielo'),
                "cielo_error": response_json
            }), response.status_code

    except Exception as e:
        print(f"Erro INESPERADO na rota do PIX: {type(e).__name__}: {e}")
        print("Detalhes completos do traceback:")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro interno no backend. Detalhes: {str(e)}", "exception_type": type(e).__name__}), 500


# --- ROTA PARA BOLETO ---
@app.route('/processar-boleto', methods=['POST'])
def processar_boleto():
    try:
        data = request.get_json()

        if not isinstance(data, dict) or not data:
            print(f"Erro: Payload JSON recebido não é um dicionário ou está vazio. Tipo: {type(data)}")
            return jsonify({"error": "Dados inválidos ou incompletos. Esperado um objeto JSON."}), 400

        if not data or 'paymentDetails' not in data or 'billingData' not in data:
            return jsonify({"error": "Dados inválidos ou incompletos"}), 400

        payment_details = data['paymentDetails'] # Contém amount, customer, address
        billing_data = data['billingData']

        amount_in_cents = int(float(payment_details['amount']) * 100)
        merchant_order_id = f"LV_BOLETO_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

        # Data de vencimento do boleto (ex: 5 dias a partir de hoje)
        due_date = (datetime.date.today() + datetime.timedelta(days=5)).strftime('%Y-%m-%d')

        # Construa o payload para o Boleto (Cielo espera um formato específico)
        boleto_data = {
            "MerchantOrderId": merchant_order_id,
            "Customer": {
                "Name": f"{billing_data.get('firstName')} {billing_data.get('lastName')}",
                "Identity": billing_data.get('cpf'),
                "IdentityType": "CPF",
                "Email": billing_data.get('email'),
                "Address": { # Endereço do cliente para o boleto
                    "Street": billing_data.get('address'),
                    "Number": billing_data.get('number'),
                    "Complement": billing_data.get('complement'),
                    "ZipCode": billing_data.get('zipCode'),
                    "District": billing_data.get('neighborhood'),
                    "City": billing_data.get('city', 'SAO PAULO'), # Sugestão: adicione 'city' ao billingData do frontend
                    "State": billing_data.get('state', 'SP'),     # Sugestão: adicione 'state' ao billingData do frontend
                    "Country": billing_data.get('country', 'BRA')
                }
            },
            "Payment": {
                "Type": "Boleto",
                "Amount": amount_in_cents,
                "BoletoNumber": f"000000{os.urandom(3).hex()}", # Gerar um número de boleto interno
                # "BarCodeNumber": "", # A Cielo preenche (Não enviar no request)
                # "DigitableLine": "", # A Cielo preenche (Não enviar no request)
                "Demonstrative": "Pagamento referente à compra na Livraria Web",
                "Instructions": "Não receber após o vencimento",
                "Provider": "Bradesco", # Exemplo: Cielo aceita vários bancos, verifique a docs
                "ExpirationDate": due_date
            }
        }

        headers = {
            "Content-Type": "application/json",
            "MerchantId": MERCHANT_ID,
            "MerchantKey": MERCHANT_KEY
        }

        print(f"Enviando para Cielo (Boleto): {json.dumps(boleto_data, indent=2)}")

        response = requests.post(CIELO_API_URL, headers=headers, data=json.dumps(boleto_data))
        
        # --- Tratamento de erro para resposta não-JSON ---
        try:
            response_json = response.json()
        except json.JSONDecodeError:
            print(f"Erro: Resposta da Cielo não é JSON válido. Status: {response.status_code}, Conteúdo: {response.text}")
            return jsonify({
                "status": "error",
                "message": f"Erro inesperado da Cielo. Status: {response.status_code}. Conteúdo: {response.text[:200]}...",
                "cielo_error": {"raw_response": response.text, "status_code": response.status_code}
            }), 502
        # --- FIM DO BLOCO DE TRATAMENTO DE JSON ---

        print(f"Resposta da Cielo (Boleto): {json.dumps(response_json, indent=2)}")

        # --- MODIFICAÇÃO PRINCIPAL: Trata respostas de erro da Cielo que são LISTAS ---
        if isinstance(response_json, list) and response_json:
            first_error = response_json[0]
            error_message = first_error.get('Message', 'Erro desconhecido na lista de erros da Cielo (Boleto)')
            error_code = first_error.get('Code', 'N/A')
            return jsonify({
                "status": "error",
                "message": f"Erro da Cielo (Boleto): {error_message} (Código: {error_code})",
                "cielo_error": response_json
            }), response.status_code

        if response.status_code == 201: # 201 Created é o esperado para sucesso na criação do Boleto
            # Verifique se a URL do boleto está presente (BarCodeNumber e DigitableLine também virão)
            boleto_url = response_json.get('Payment', {}).get('Url')
            bar_code_number = response_json.get('Payment', {}).get('BarCodeNumber')
            digitable_line = response_json.get('Payment', {}).get('DigitableLine')

            if boleto_url:
                return jsonify({
                    "status": "success",
                    "message": "Boleto gerado com sucesso!",
                    "cielo_response": response_json,
                    "boleto_url": boleto_url,
                    "bar_code_number": bar_code_number,
                    "digitable_line": digitable_line
                }), 200
            else:
                return jsonify({
                    "status": "error",
                    "message": "Erro ao gerar Boleto: URL do boleto não encontrada na resposta.",
                    "cielo_error": response_json
                }), response.status_code
        else:
            return jsonify({
                "status": "error",
                "message": response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar Boleto na Cielo'),
                "cielo_error": response_json
            }), response.status_code

    except Exception as e:
        print(f"Erro INESPERADO na rota do BOLETO: {type(e).__name__}: {e}")
        print("Detalhes completos do traceback:")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro interno no backend. Detalhes: {str(e)}", "exception_type": type(e).__name__}), 500

if __name__ == '__main__':
    # No ambiente local de desenvolvimento, este trecho é executado
    # Para carregar variáveis de ambiente localmente, você pode usar a biblioteca `python-dotenv`.
    # Adicione `from dotenv import load_dotenv` no topo e `load_dotenv()` antes de app.run()
    # (Lembre-se de adicionar 'python-dotenv' ao requirements.txt e '.env' ao .gitignore)
    app.run(debug=True, port=5000)