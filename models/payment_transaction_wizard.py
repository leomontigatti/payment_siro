from odoo import fields, models


class PaymentTransactionWizard(models.TransientModel):
    _name = "payment.transaction.wizard"
    _description = "Modelo para procesar transacciones manualmente"

    date_from = fields.Date(string="Fecha Desde", required=True)
    date_to = fields.Date(string="Fecha Hasta", required=True)

    def process_transactions_manually(self):
        self.ensure_one()
        payment_transaction = self.env["payment.transaction"]
        payment_transaction._process_transactions(self.date_from, self.date_to)
