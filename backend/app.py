from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import os
import datetime

app = Flask(__name__)
CORS(app) # Habilita CORS para todas as rotas da sua aplicação Flask

# Suas credenciais da Cielo (já estão corretas)
MERCHANT_ID = "6542d0f6-f606-440b-a96e-7fd5a4ec8155"
MERCHANT_KEY = "VHMAvxtYBypBBeKhEsz28NDH1JF0NshheALbnUch"

# URLs da API Cielo (PARA PRODUÇÃO)
CIELO_API_URL = "https://api.cieloecommerce.cielo.com.br/1/sales/"
CIELO_API_QUERY_URL = "https://apiquery.cieloecommerce.cielo.com.br/1/sales/"

@app.route('/')
def home():
    return "Backend Cielo funcionando! Acesse /processar-pagamento, /processar-pix ou /processar-boleto."

# --- ROTA PARA CARTÃO DE CRÉDITO ---
@app.route('/processar-pagamento', methods=['POST'])
def processar_pagamento():
    try:
        data = request.get_json()

        if not data or 'paymentDetails' not in data or 'billingData' not in data:
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
                    "City": "CIDADE", # Você precisaria obter a cidade e estado via CEP ou outro campo
                    "State": "XX",    # Você precisaria obter a cidade e estado via CEP ou outro campo
                    "Country": billing_data.get('country', 'BRA')
                },
                "DeliveryAddress": { # Pode ser o mesmo do cliente, se não houver um endereço de entrega separado
                    "Street": billing_data.get('address'),
                    "Number": billing_data.get('number'),
                    "Complement": billing_data.get('complement'),
                    "ZipCode": billing_data.get('zipCode'),
                    "District": billing_data.get('neighborhood'),
                    "City": "CIDADE",
                    "State": "XX",
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
                    "ExpirationDate": payment_details['expirationDate'], # MM/AAAA
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
        response_json = response.json()

        print(f"Resposta da Cielo (Cartão): {json.dumps(response_json, indent=2)}")

        # A Cielo retorna 201 Created para sucesso de autorização
        if response.status_code == 201 and response_json.get('Payment', {}).get('Status') == 2: # Status 2 = Autorizado
            return jsonify({
                "status": "success",
                "message": "Pagamento com cartão processado com sucesso!",
                "cielo_response": response_json
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar pagamento com cartão na Cielo'),
                "cielo_error": response_json
            }), response.status_code

    except Exception as e:
        print(f"Erro inesperado no cartão: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ROTA PARA PIX ---
@app.route('/processar-pix', methods=['POST'])
def processar_pix():
    try:
        data = request.get_json()

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
        response_json = response.json()

        print(f"Resposta da Cielo (Pix): {json.dumps(response_json, indent=2)}")

        if response.status_code == 201: # 201 Created é o esperado para sucesso na criação do Pix
            # Verifique se a string do QR Code está presente
            qr_code_string = response_json.get('Payment', {}).get('QrCodeString')
            if qr_code_string:
                return jsonify({
                    "status": "success",
                    "message": "QR Code Pix gerado com sucesso!",
                    "cielo_response": response_json
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
        print(f"Erro inesperado no Pix: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ROTA PARA BOLETO ---
@app.route('/processar-boleto', methods=['POST'])
def processar_boleto():
    try:
        data = request.get_json()

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
                    "City": "CIDADE", # Você precisaria obter a cidade e estado via CEP ou outro campo
                    "State": "XX",    # Você precisaria obter a cidade e estado via CEP ou outro campo
                    "Country": billing_data.get('country', 'BRA')
                }
            },
            "Payment": {
                "Type": "Boleto",
                "Amount": amount_in_cents,
                "BoletoNumber": f"000000{os.urandom(3).hex()}", # Gerar um número de boleto interno
                "BarCodeNumber": "", # A Cielo preenche
                "DigitableLine": "", # A Cielo preenche
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
        response_json = response.json()

        print(f"Resposta da Cielo (Boleto): {json.dumps(response_json, indent=2)}")

        if response.status_code == 201: # 201 Created é o esperado para sucesso na criação do Boleto
            # Verifique se a URL do boleto está presente
            boleto_url = response_json.get('Payment', {}).get('Url')
            if boleto_url:
                return jsonify({
                    "status": "success",
                    "message": "Boleto gerado com sucesso!",
                    "cielo_response": response_json
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
        print(f"Erro inesperado no Boleto: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)