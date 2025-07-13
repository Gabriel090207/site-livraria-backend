# NOVO CONTEÚDO PARA backend/app.py (AGORA EM FASTAPI)
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import json
import os
import datetime

# Cria a instância da aplicação FastAPI
app = FastAPI()

# Configuração do CORS para permitir requisições do seu front-end local
# Em produção, você DEVE substituir "*" pela URL específica do seu front-end (e.g., "https://seudominio.com")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"], # Permite todos os métodos (GET, POST, etc.)
    allow_headers=["*"], # Permite todos os cabeçalhos
)

# Suas credenciais da Cielo
# Lidas de variáveis de ambiente do sistema, com fallback para valores padrão para desenvolvimento local.
MERCHANT_ID = os.environ.get("MERCHANT_ID", "6542d0f6-f606-440b-a96e-7fd5a4ec8155")
MERCHANT_KEY = os.environ.get("MERCHANT_KEY", "VHMAvxtYBypBBeKhEsz28NDH1JF0NshheALbnUch")

# URLs da API Cielo (PARA PRODUÇÃO)
CIELO_API_URL = "https://api.cieloecommerce.cielo.com.br/1/sales/"
CIELO_API_QUERY_URL = "https://apiquery.cieloecommerce.cielo.com.br/1/sales/"

@app.get("/")
async def home():
    """Rota de teste para verificar se o backend está ativo."""
    return {"message": "Backend Cielo com FastAPI funcionando! Acesse /processar-pagamento, /processar-pix ou /processar-boleto."}

# --- ROTA PARA CARTÃO DE CRÉDITO ---
@app.post("/processar-pagamento")
async def processar_pagamento(request: Request):
    """
    Processa um pagamento com Cartão de Crédito via API Cielo.
    Recebe dados de cobrança e detalhes do cartão do front-end.
    """
    try:
        data = await request.json() # Usa await para ler o corpo JSON de uma requisição assíncrona

        if not data or 'paymentDetails' not in data or 'billingData' not in data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "Dados inválidos ou incompletos"})

        payment_details = data['paymentDetails']
        billing_data = data['billingData']

        # Validação básica dos campos de pagamento de cartão
        if 'cardNumber' not in payment_details or 'holder' not in payment_details or \
           'expirationDate' not in payment_details or 'securityCode' not in payment_details or \
           'amount' not in payment_details:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "Dados de pagamento do cartão incompletos"})

        card_number = payment_details['cardNumber'].replace(" ", "").replace("-", "")
        amount_in_cents = int(float(payment_details['amount']) * 100)
        installments = payment_details.get('installments', 1)

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
                    "City": "BRODOWSKI", # TODO: Obter a cidade via API de CEP ou de um campo no front-end
                    "State": "SP",    # TODO: Obter o estado via API de CEP ou de um campo no front-end
                    "Country": billing_data.get('country', 'BRA')
                },
                "DeliveryAddress": {
                    "Street": billing_data.get('address'),
                    "Number": billing_data.get('number'),
                    "Complement": billing_data.get('complement'),
                    "ZipCode": billing_data.get('zipCode'),
                    "District": billing_data.get('neighborhood'),
                    "City": "BRODOWSKI",
                    "State": "SP",
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
                    "ExpirationDate": payment_details['expirationDate'],
                    "SecurityCode": payment_details['securityCode'],
                    "Brand": "Visa" # Cielo pode auto-detectar, mas é bom enviar
                }
            }
        }

        headers = {
            "Content-Type": "application/json",
            "MerchantId": MERCHANT_ID,
            "MerchantKey": MERCHANT_KEY
        }

        print(f"Enviando para Cielo (Cartão): {json.dumps(payment_data, indent=2)}")

        # requests é síncrono, mas FastAPI o executa em um threadpool para não bloquear
        response = requests.post(CIELO_API_URL, headers=headers, data=json.dumps(payment_data))
        response_json = response.json()

        print(f"Resposta da Cielo (Cartão): {json.dumps(response_json, indent=2)}")

        # A Cielo retorna 201 Created para sucesso de autorização
        if response.status_code == status.HTTP_201_CREATED and response_json.get('Payment', {}).get('Status') == 2: # Status 2 = Autorizado
            return JSONResponse(status_code=status.HTTP_200_OK, content={
                "status": "success",
                "message": "Pagamento com cartão processado com sucesso!",
                "cielo_response": response_json
            })
        else:
            # Captura a mensagem de retorno da Cielo para exibir no front-end
            return_message = response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar pagamento com cartão na Cielo')
            return_code = response_json.get('Payment', {}).get('ReturnCode', 'N/A')
            
            raise HTTPException(status_code=response.status_code, detail={
                "status": "error",
                "message": f"Erro Cielo ({return_code}): {return_message}",
                "cielo_error": response_json
            })

    except HTTPException as e:
        raise e # Re-lança HTTPException para o FastAPI lidar
    except Exception as e:
        print(f"Erro inesperado no cartão: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"status": "error", "message": str(e)})


# --- ROTA PARA PIX ---
@app.post("/processar-pix")
async def processar_pix(request: Request):
    """
    Processa um pagamento Pix via API Cielo, gerando um QR Code.
    """
    try:
        data = await request.json()

        if not data or 'paymentDetails' not in data or 'billingData' not in data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "Dados inválidos ou incompletos"})

        payment_details = data['paymentDetails']
        billing_data = data['billingData']

        amount_in_cents = int(float(payment_details['amount']) * 100)
        merchant_order_id = f"LV_PIX_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

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

        if response.status_code == status.HTTP_201_CREATED:
            qr_code_string = response_json.get('Payment', {}).get('QrCodeString')
            if qr_code_string:
                return JSONResponse(status_code=status.HTTP_200_OK, content={
                    "status": "success",
                    "message": "QR Code Pix gerado com sucesso!",
                    "cielo_response": response_json
                })
            else:
                raise HTTPException(status_code=response.status_code, detail={
                    "status": "error",
                    "message": "Erro ao gerar QR Code Pix: QR Code não encontrado na resposta.",
                    "cielo_error": response_json
                })
        else:
            return_message = response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar Pix na Cielo')
            return_code = response_json.get('Payment', {}).get('ReturnCode', 'N/A')
            raise HTTPException(status_code=response.status_code, detail={
                "status": "error",
                "message": f"Erro Cielo ({return_code}): {return_message}",
                "cielo_error": response_json
            })

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Erro inesperado no Pix: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"status": "error", "message": str(e)})


# --- ROTA PARA BOLETO ---
@app.post("/processar-boleto")
async def processar_boleto(request: Request):
    """
    Processa um pagamento via Boleto Bancário, gerando a URL do boleto.
    """
    try:
        data = await request.json()

        if not data or 'paymentDetails' not in data or 'billingData' not in data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "Dados inválidos ou incompletos"})

        payment_details = data['paymentDetails']
        billing_data = data['billingData']

        amount_in_cents = int(float(payment_details['amount']) * 100)
        merchant_order_id = f"LV_BOLETO_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

        due_date = (datetime.date.today() + datetime.timedelta(days=5)).strftime('%Y-%m-%d')

        boleto_data = {
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
                    "City": "BRODOWSKI", # TODO: Obter a cidade via API de CEP ou de um campo no front-end
                    "State": "SP",    # TODO: Obter o estado via API de CEP ou de um campo no front-end
                    "Country": billing_data.get('country', 'BRA')
                }
            },
            "Payment": {
                "Type": "Boleto",
                "Amount": amount_in_cents,
                "BoletoNumber": f"000000{os.urandom(3).hex()}", # Gerar um número de boleto interno
                "BarCodeNumber": "", # Cielo preenche
                "DigitableLine": "", # Cielo preenche
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

        if response.status_code == status.HTTP_201_CREATED:
            boleto_url = response_json.get('Payment', {}).get('Url')
            if boleto_url:
                return JSONResponse(status_code=status.HTTP_200_OK, content={
                    "status": "success",
                    "message": "Boleto gerado com sucesso!",
                    "cielo_response": response_json
                })
            else:
                raise HTTPException(status_code=response.status_code, detail={
                    "status": "error",
                    "message": "Erro ao gerar Boleto: URL do boleto não encontrada na resposta.",
                    "cielo_error": response_json
                })
        else:
            return_message = response_json.get('Payment', {}).get('ReturnMessage', 'Erro ao processar Boleto na Cielo')
            return_code = response_json.get('Payment', {}).get('ReturnCode', 'N/A')
            raise HTTPException(status_code=response.status_code, detail={
                "status": "error",
                "message": f"Erro Cielo ({return_code}): {return_message}",
                "cielo_error": response_json
            })

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Erro inesperado no Boleto: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"status": "error", "message": str(e)})

# O if __name__ == '__main__': app.run(debug=True, port=5000) não é usado com Uvicorn/FastAPI
# O Uvicorn é iniciado via linha de comando (ou Procfile)