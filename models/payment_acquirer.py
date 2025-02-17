import logging
from datetime import timedelta

import requests
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PaymentAcquirerSIRO(models.Model):
    _inherit = "payment.acquirer"

    provider = fields.Selection(selection_add=[("siro", "SIRO")], ondelete="set null")
    siro_username = fields.Char(
        string="Usuario SIRO",
        help="CUIT del administrador de SIRO.",
    )
    siro_nro_empresa = fields.Char(
        string="Número de convenio SIRO",
        help="Número de identificación del convenio (compuesto por los 10 dígitos que identifican al convenio, provistos por el banco).",
    )
    siro_password = fields.Char(
        string="Contraseña SIRO",
        help="Proporcionado por SIRO al momento del pasaje a producción, solicitar a mesadeayuda@bancoroela.com.ar",
    )
    siro_access_token = fields.Char(string="Token de la API", readonly=True)
    siro_access_token_expiry = fields.Datetime(
        string="Fecha de caducidad del token", readonly=True
    )

    @api.depends("siro_username", "siro_password")
    def _get_access_token(self):
        if (
            self.siro_access_token
            and fields.Datetime.now() < self.siro_access_token_expiry
        ):
            return

        SESSION_URL = "https://apisesion.bancoroela.com.ar/auth/sesion"
        headers = {"Content-Type": "application/json"}
        payload = {"Usuario": self.siro_username, "Password": self.siro_password}

        try:
            response = requests.post(SESSION_URL, headers=headers, json=payload)
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

        json_response = response.json()
        access_token = json_response.get("access_token")
        if not access_token:
            _logger.error("No se pudo obtener el token de acceso.")
            return False

        self.write(
            {
                "siro_access_token": access_token,
                "siro_access_token_expiry": fields.Datetime.now()
                + timedelta(seconds=json_response.get("expires_in")),
            }
        )

        _logger.info("Token de acceso SIRO actualizado.")
