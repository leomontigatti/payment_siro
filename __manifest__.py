{
    "name": "SIRO Payment Integration",
    "version": "1.2",
    "summary": "Integration with SIRO for payment processing",
    "category": "Accounting/Payment Acquirers",
    "author": "Franco",
    "depends": ["account", "payment", "account_payment_group"],
    "data": [
        "security/ir.model.access.csv",
        "views/siro_acquirer_views.xml",
        "data/siro_journal_data.xml",
        "data/payment_acquirer_data.xml",
    ],
    "installable": True,
    "application": True,
}
