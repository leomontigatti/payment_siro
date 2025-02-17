import logging
from datetime import timedelta

import requests
from odoo import fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransactionSIRO(models.Model):
    _inherit = "payment.transaction"

    siro_reference_string = fields.Char("String de referencia SIRO", readonly=True)

    def _create_transaction(self, payment_string):
        acquirer = self.env["payment.acquirer"].search(
            [("provider", "=", "siro")], limit=1
        )
        partner = self.env["res.partner"].search(
            [("internal_code", "=", payment_string[37:43])], limit=1
        )
        amount = float(payment_string[24:35]) / 100
        date = f"{payment_string[0:4]}-{payment_string[4:6]}-{payment_string[6:8]}"
        invoices = self.env["account.move"].search(
            [("partner_id", "=", partner.id), ("amount_residual", "!=", 0)]
        )
        currency = self.env["res.currency"].search([("name", "=", "ARS")], limit=1)
        payment_method = "transferencia." if payment_string[123:126] == "TI" else ""

        try:
            self.create(
                {
                    "acquirer_id": acquirer.id,
                    "amount": amount,
                    "reference": f"Pago por {payment_method}. Importe: ${amount}. Fecha de pago: {date}.",
                    "state": "done",
                    "type": "server2server",
                    "partner_id": partner.id,
                    "date": date,
                    "invoice_ids": invoices.ids,
                    "currency_id": currency.id,
                    "siro_reference_string": payment_string,
                }
            )
        except ValidationError as e:
            _logger.error(
                f"No se pudo crear la transacción. Detalles del error: {e.msg}"
            )
            return False

        return True

    def _process_transactions(self):
        acquirer = self.env["payment.acquirer"].search(
            [("provider", "=", "siro")], limit=1
        )

        if not acquirer or not acquirer.state == "enabled":
            _logger.warning("El método de pago SIRO no está configurado o habilitado.")
            return False

        RENDICION_URL = "https://apisiro.bancoroela.com.ar/siro/listados/proceso"
        acquirer._get_access_token()

        today = fields.Datetime.now()
        yesterday = today - timedelta(days=1)

        headers = {
            "Authorization": f"Bearer {acquirer.siro_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "fecha_desde": yesterday.strftime("%Y-%m-%d"),
            "fecha_hasta": today.strftime("%Y-%m-%d"),
            "cuit_administrador": acquirer.siro_username,
            "nro_empresa": acquirer.siro_nro_empresa,
        }

        try:
            response = requests.post(RENDICION_URL, json=payload, headers=headers)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                message = response.json().get("message", "")
                _logger.error(
                    f"Error en la comunicación con la API. Detalles: {message}"
                )
                return False
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.error("No se pudo establecer la conexión con la API.")
            return False

        payments = response.json()
        transactions_amount = 0
        for payment in payments:
            transaction_created = self._create_transaction(
                payment[0:8], payment[24:35], payment[37:43], payment[123:126]
            )
            transactions_amount += 1 if transaction_created else 0

        success_msg = "Proceso de transacciones SIRO completado."
        if transactions_amount:
            _logger.info(
                f"{success_msg} Se crearon {transactions_amount} transacciones."
            )
        else:
            _logger.info(f"{success_msg} No se crearon transacciones nuevas.")
