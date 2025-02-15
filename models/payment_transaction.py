from datetime import timedelta

import requests
from odoo import fields, models
from odoo.exceptions import ValidationError


class PaymentTransactionSIRO(models.Model):
    _inherit = "payment.transaction"

    payment_method = fields.Char("Medio de pago")

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
        for record in json_response:
            partner = self.env["res.partner"].search(
                "internal_code", "=", record[37:43]
            )
            self.create(
                {
                    "date": record[0:8],
                    "amount": record[24:35],
                    "partner_id": partner.id,
                    "payment_id": record[103:123],
                    "payment_method": record[123:126],
                    "type": "server2server",
                    "partner_country_id": partner.country_id.id,
                    "acquirer_id": 1,  # Buscar el ID del acquirer de SIRO
                    "currency_id": self.currency_id.id,  # Buscar el ID de la moneda ARS
                    "reference": f"Pago por SIRO. Medio de pago: {record[123:126]}. Importe: ${record[24:35]}. Estado: aprobado, ID de Pago: {record[103:123]}",
                    "state": "done",
                }
            )

    def _create_transactions(
        self, payment_date, ammount_paid, customer_id, payment_id, payment_method
    ):
        # account_payment_group = self.env["account.payment.group"]
        existing_transaction = self.search(["payment_id", "=", payment_id], limit=1)

        if not existing_transaction:
            self.create(
                {
                    "acquirer_id": 1,  # Buscar el ID del acquirer de SIRO
                    "amount": ammount_paid,
                    "currency_id": 19,  # Buscar el ID de la moneda ARS
                    "partner_country_id": 1,  # Buscar el ID del país Argentina
                    "reference": f"Pago por SIRO. Medio de pago: {payment_method}. Importe: ${ammount_paid}. Estado: approved, ID de Pago: {payment_id}",
                    "state": "done",
                    "type": "inbound",
                    "partner_id": customer_id,
                    "payment_id": payment_id,
                    "date": payment_date,
                    "siro_payment_method": payment_method,
                }
            )

            # receipt = account_payment_group.create(
            #     {
            #         "company_id": 1,
            #         "receiptbook_id": 2,
            #         "payment_date": payment_date,
            #         "communication": receipt_id,
            #         "notes": f"Pago por SIRO. Medio de pago: {payment_method}. Importe: ${ammount_paid}. Estado: approved, ID de Pago: {receipt_id}",
            #         "partner_id": customer_id,
            #         "partner_type": "customer",
            #         "commercial_partner_id": customer_id,
            #         "payment_ids": [
            #             (
            #                 0,
            #                 0,
            #                 {
            #                     "payment_type": "inbound",
            #                     "partner_type": "customer",
            #                     "payment_date": payment_date,
            #                     "partner_id": customer_id,
            #                     "communication": receipt_id,
            #                     "amount": ammount_paid,
            #                     "currency_id": 19,
            #                     "journal_id": 129,
            #                     "payment_method_id": 1,
            #                 },
            #             )
            #         ],
            #     }
            # )
            # account_payment_group.add_all(receipt)
            # account_payment_group.post(receipt)

    def check_transaction_status(self, transaction_id):
        acquirer = self.env["payment.acquirer"].search(
            [("provider", "=", "siro")], limit=1
        )
        acquirer._get_access_token()

        STATUS_URL = f"https://apisiro.bancoroela.com.ar/siro/pagos/{transaction_id}"
        headers = {
            "Authorization": f"Bearer {acquirer.siro_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(STATUS_URL, headers=headers)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                message = response.json().get("message", "")
                raise ValidationError(
                    f"Error en la comunicación con la API. Detalles: {message}"
                )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            raise ValidationError("No se pudo establecer la conexión con la API.")

        return response.json().get("Estado")

    def update_transaction_status(self):
        transactions = self.search([("siro_transaction_status", "=", "pending")])
        for transaction in transactions:
            siro_status = self.check_transaction_status(transaction.siro_transaction_id)
            if siro_status == "PROCESADA":
                transaction.siro_status = "processed"
            elif siro_status == "CANCELADA":
                transaction.siro_status = "canceled"
            else:
                transaction.siro_status = "error"
