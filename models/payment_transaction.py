from datetime import timedelta

import requests
from odoo import fields, models
from odoo.exceptions import ValidationError


class PaymentTransactionSIRO(models.Model):
    _inherit = "payment.transaction"

    def _get_partner_invoices(self, partner_id):
        invoices_ids = []
        invoices = self.env["account.move"].search(
            [("partner_id", "=", partner_id), ("amount_residual", "!=", 0)]
        )
        for invoice in invoices:
            invoices_ids.append(invoice.id)

        return invoices_ids

    def _create_transactions(
        self,
        payment_date,
        ammount,
        customer_id,
    ):
        acquirer = self.env["payment.acquirer"].search([("provider", "=", "siro")])
        partner = self.env["res.partner"].search([("internal_code", "=", customer_id)])

        self.create(
            {
                "acquirer_id": acquirer.id,
                "amount": ammount,
                "reference": f"Pago por transferencia SIRO. Importe: ${ammount}.",
                "state": "done",
                "type": "inbound",
                "partner_id": partner.id,
                "date": payment_date,
                "invoice_ids": self._get_partner_invoices(partner.id),
            }
        )

    def _process_transactions(self):
        RENDICION_URL = "https://apisiro.bancoroela.com.ar/siro/listados/proceso"
        acquirer = self.env["payment.acquirer"].search(
            [("provider", "=", "siro")], limit=1
        )
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
                raise ValidationError(
                    f"Error en la comunicación con la API. Detalles: {message}"
                )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            raise ValidationError("No se pudo establecer la conexión con la API.")

        json_response = response.json()
        for payment in json_response:
            self._create_transactions(payment[0:8], payment[24:35], payment[37:43])
