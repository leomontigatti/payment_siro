{
    "name": "SIRO Payment Integration",
    "version": "1.2",
    "summary": "Integration with SIRO for payment processing",
    "category": "Accounting/Payment Acquirers",
    "author": "Franco",
    "depends": ["account", "payment", "account_payment_group"],
    "data": [
        "security/ir.model.access.csv",
        "data/siro_journal_data.xml",
        "data/payment_acquirer_data.xml",
        "data/cron_process_transactions.xml",
        "views/siro_acquirer_views.xml",
        "views/payment_transaction.xml",
    ],
    "installable": True,
    "application": True,
}
