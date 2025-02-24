import logging
from datetime import date, datetime, timedelta
from dateutil import relativedelta

import requests
from odoo import fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransactionSIRO(models.Model):
    _inherit = "payment.transaction"

    siro_payment_id = fields.Char("ID de pago SIRO", readonly=True)

    def _create_transaction(
        self, payment_date, paid_amount, customer_id, payment_method, payment_id
    ):
        acquirer = self.env["payment.acquirer"].search(
            [("provider", "=", "siro")], limit=1
        )
        partner = self.env["res.partner"].search(
            [("internal_code", "=", customer_id)], limit=1
        )
        date_time = datetime.strptime(payment_date, "%Y%m%d")
        amount = float(paid_amount) / 100
        invoices = self.env["account.move"].search(
            [("partner_id", "=", partner.id), ("amount_residual", "!=", 0)]
        )
        currency = self.env["res.currency"].search([("name", "=", "ARS")], limit=1)
        method = "Pago por transferencia. " if payment_method == "TI " else ""

        if self.search([("siro_payment_id", "=", payment_id)], limit=1):
            _logger.info(f"La transacción con ID {payment_id} ya existe en el sistema.")
            return False

        try:
            self.create(
                {
                    "acquirer_id": acquirer.id,
                    "amount": amount,
                    "reference": f"{method}Importe: ${amount}. Fecha de pago: {payment_date[6:8]}/{payment_date[4:6]}/{payment_date[0:4]}.",
                    "state": "done",
                    "type": "server2server",
                    "partner_id": partner.id,
                    "date": date_time,
                    "invoice_ids": invoices.ids,
                    "currency_id": currency.id,
                    "siro_payment_id": payment_id,
                }
            )
        except ValidationError as e:
            _logger.error(
                f"No se pudo crear la transacción. Detalles del error: {e.msg}"
            )
            return False

        return True

    def _process_transactions(self, date_from=None, date_to=None):
        acquirer = self.env["payment.acquirer"].search(
            [("provider", "=", "siro")], limit=1
        )

        if not acquirer or not acquirer.state == "enabled":
            _logger.warning("El método de pago SIRO no está configurado o habilitado.")
            return False

        RENDICION_URL = "https://apisiro.bancoroela.com.ar/siro/listados/proceso"
        acquirer._get_access_token()

        today = date.today()
        yesterday = today - timedelta(days=1)

        headers = {
            "Authorization": f"Bearer {acquirer.siro_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "fecha_desde": (
                fields.Date.to_string(date_from)
                if date_from
                else yesterday.strftime("%Y-%m-%d")
            ),
            "fecha_hasta": (
                fields.Date.to_string(date_to)
                if date_to
                else today.strftime("%Y-%m-%d")
            ),
            "cuit_administrador": acquirer.siro_username,
            "nro_empresa": acquirer.siro_nro_empresa,
        }

        try:
            response = requests.post(RENDICION_URL, json=payload, headers=headers)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                _logger.error(
                    "Error en la comunicación con la API. Por favor revise las credenciales."
                )
                return False
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.error("No se pudo establecer la conexión con la API.")
            return False

        payments = response.json()
        transactions_amount = 0
        for payment in payments:
            transaction_created = self._create_transaction(
                payment[0:8],
                payment[24:35],
                payment[37:43],
                payment[123:126],
                payment[226:236],
            )
            transactions_amount += 1 if transaction_created else 0

        success_msg = "Proceso de transacciones SIRO completado."
        if transactions_amount:
            _logger.info(
                f"{success_msg} Se crearon {transactions_amount} transacciones."
            )
        else:
            _logger.info(f"{success_msg} No se crearon transacciones nuevas.")


    def _post_process_after_done(self):
        self._reconcile_after_transaction_done()
        self._log_payment_transaction_received()
        self.write({'is_processed': True})
        return True


    def _cron_post_process_after_done(self):
        if not self:
            ten_minutes_ago = datetime.now() - relativedelta.relativedelta(minutes=10)
            # we don't want to forever try to process a transaction that doesn't go through
            retry_limit_date = datetime.now() - relativedelta.relativedelta(days=30)
            # we retrieve all the payment tx that need to be post processed
            self = self.search([('state', '=', 'done'),
                                ('is_processed', '=', False),
                                ('date', '<=', ten_minutes_ago),
                                ('date', '>=', retry_limit_date),
                            ])
        for tx in self:
            try:
                tx._post_process_after_done()
                self.env.cr.commit()
            except Exception as e:
                _logger.exception("Transaction post processing failed")
                self.env.cr.rollback()
